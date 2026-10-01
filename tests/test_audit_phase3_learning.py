"""Audit phase 3: districts/learning regression tests (no network, no downloads)."""
import sys
import uuid
import threading
import asyncio
import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.agent_base import AgentBase


def _bare(cls, name, tmp_path):
    with patch("core.memory.episodic.EpisodicMemory", return_value=MagicMock()), \
         patch("core.memory.obsidian_sync.ObsidianSync", return_value=MagicMock()):
        agent = cls.__new__(cls)
        AgentBase.__init__(agent, str(uuid.uuid4()), name, "learning")
    agent.memory = MagicMock()
    agent.obsidian = MagicMock()
    return agent


def _video(tmp_path):
    from districts.learning.video_ingestor import VideoIngestor
    a = _bare(VideoIngestor, "VideoIngestor", tmp_path)
    a.download_dir = tmp_path / "lectures"
    a.download_dir.mkdir()
    a.transcripts_dir = tmp_path / "transcripts"
    a.transcripts_dir.mkdir()
    return a


def _course(tmp_path):
    from districts.learning.course_tracker import CourseTracker
    a = _bare(CourseTracker, "CourseTracker", tmp_path)
    a._lock = threading.RLock()
    a.db_path = tmp_path / "c.db"
    a._init_db()
    return a


# ---------------- VideoIngestor ----------------

class _FakeResp:
    def __init__(self, status, body=b"<html>not found</html>"):
        self.status, self.body = status, body

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def iter_bytes(self, chunk_size=8192):
        yield self.body


@contextlib.contextmanager
def _stream(status):
    yield _FakeResp(status)


def test_http_404_body_not_reported_as_downloaded_video(tmp_path):
    a = _video(tmp_path)
    with patch("httpx.stream", side_effect=lambda *x, **k: _stream(404)):
        r = a.download_lecture("https://example.com/missing.mp4")
    assert r["download_status"] == "failed"
    assert r["video_path"] is None
    assert not list(a.download_dir.iterdir())
    assert a.memory.store.call_args.kwargs["event_type"] == "lecture_download_failed"


def test_download_blocks_ssrf_and_option_urls(tmp_path):
    a = _video(tmp_path)
    with patch("subprocess.run") as run, patch("httpx.stream") as hs:
        for u in ("http://169.254.169.254/latest/meta-data", "http://127.0.0.1:8000/x.mp4",
                  "--exec=touch /tmp/pwn youtube.com", "file:///etc/passwd"):
            r = a.download_lecture(u)
            assert r["download_status"] == "failed"
        run.assert_not_called()
        hs.assert_not_called()


def test_ytdlp_url_passed_after_double_dash(tmp_path):
    a = _video(tmp_path)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return MagicMock(returncode=0, stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        a.download_lecture("https://www.youtube.com/watch?v=abc")
    dl = [c for c in calls if "--version" not in c][0]
    assert dl[-2:] == ["--", "https://www.youtube.com/watch?v=abc"]


def test_transcript_failure_is_error_not_canned_success(tmp_path):
    a = _video(tmp_path)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    with patch("subprocess.run", side_effect=FileNotFoundError):
        r = a.extract_transcript(str(v))
    assert "error" in r and "transcript_preview" not in r
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="boom")):
        r = a.extract_transcript(str(v))
    assert "error" in r and "transcript_preview" not in r
    # rc 0 but no output file
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
        r = a.extract_transcript(str(v))
    assert "error" in r
    a.memory.store.assert_not_called()


def test_transcript_read_from_whisper_output_name(tmp_path):
    a = _video(tmp_path)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")

    def fake_run(cmd, **kw):
        (a.transcripts_dir / "v.txt").write_text("hello lecture", encoding="utf-8")
        return MagicMock(returncode=0, stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        r = a.extract_transcript(str(v))
    assert r["transcript_preview"] == "hello lecture"
    assert (a.transcripts_dir / "v_transcript.txt").read_text(encoding="utf-8") == "hello lecture"


def test_summarize_without_transcript_does_not_fabricate(tmp_path):
    a = _video(tmp_path)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    with patch.object(a, "_call_ollama", return_value="fake summary") as llm:
        r = a.summarize_lecture(str(v))
    assert "error" in r and "summary" not in r
    llm.assert_not_called()


def test_run_with_url_not_reported_ok(tmp_path):
    a = _video(tmp_path)
    r = asyncio.run(a.run({"params": {"url": "https://example.com/x.mp4"}}))
    assert r["status"] != "ok"
    assert asyncio.run(a.run({"params": None}))["status"] == "ok"


# ---------------- ConceptExtractor ----------------

def _concepts(tmp_path):
    from districts.learning.concept_extractor import ConceptExtractor
    a = _bare(ConceptExtractor, "ConceptExtractor", tmp_path)
    a.concept_graph = {}
    return a


def test_unparseable_response_not_stored_as_concept(tmp_path):
    a = _concepts(tmp_path)
    with patch.object(a, "_call_ollama", return_value="Sorry, I cannot help."):
        r = a.extract_concepts("some text")
        assert r["count"] == 0 and r["concepts"] == [] and r.get("error")
        assert a.concept_graph == {}
        a.memory.store.assert_not_called()
        r = asyncio.run(a.run({"type": "extract_concepts", "params": {"text": "t"}}))
    assert r["status"] == "error"


def test_offline_placeholder_not_counted_as_learned(tmp_path, monkeypatch):
    monkeypatch.delenv("VECTOR_LEARNING_LLM", raising=False)
    a = _concepts(tmp_path)
    r = a.extract_concepts("Neural networks learn.")
    assert r["count"] == 0 and r["concepts"] == []
    assert "offline_concept" not in a.concept_graph
    a.memory.store.assert_not_called()


def test_non_dict_concept_items_ignored(tmp_path):
    a = _concepts(tmp_path)
    with patch.object(a, "_call_ollama", return_value='["a", {"name": "x", "definition": "d"}]'):
        r = a.extract_concepts("t")
    assert r["count"] == 1 and "x" in a.concept_graph


# ---------------- CourseTracker ----------------

def test_log_lesson_unknown_course_is_error(tmp_path):
    a = _course(tmp_path)
    r = a.log_lesson("Nope", "L1")
    assert "error" in r
    a.memory.store.assert_not_called()
    r = asyncio.run(a.run({"type": "log_lesson", "params": {"course_name": "Nope", "lesson_name": "L1"}}))
    assert r["status"] == "error"


def test_re_adding_course_keeps_progress(tmp_path):
    a = _course(tmp_path)
    a.add_course("C", "Udemy", "u1")
    a.log_lesson("C", "L1")
    a.log_lesson("C", "L2")
    a.add_course("C", "Udemy", "u2")
    p = a.get_progress("C")
    assert p["completed_lessons"] == 2 and p["url"] == "u2"


def test_recent_lessons_order_by_completed_at(tmp_path):
    import sqlite3
    a = _course(tmp_path)
    a.add_course("C", "p", "u")
    conn = sqlite3.connect(str(a.db_path))
    for i in range(15):
        conn.execute("INSERT INTO lessons (course_name, lesson_name, completed_at) VALUES (?,?,?)",
                     ("C", f"L{i:02d}", f"2026-01-{i + 1:02d}T00:00:00"))
    conn.commit()
    conn.close()
    lessons = [x["lesson"] for x in a.get_progress("C")["recent_lessons"]]
    assert lessons[0] == "L14" and "L00" not in lessons


def test_empty_course_name_rejected(tmp_path):
    a = _course(tmp_path)
    assert "error" in a.add_course("  ", "p", "u")
    assert "error" in a.log_lesson("C", "")


def test_run_get_progress_missing_course_status_error(tmp_path):
    a = _course(tmp_path)
    r = asyncio.run(a.run({"type": "get_progress", "params": {"course_name": "zzz"}}))
    assert r["status"] == "error"


# ---------------- NoteOrganizer ----------------

def _notes(tmp_path):
    from districts.learning.note_organizer import NoteOrganizer
    a = _bare(NoteOrganizer, "NoteOrganizer", tmp_path)
    a.notes_index, a.links = {}, {}
    return a


def test_empty_source_dir_does_not_organize_cwd(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "n.md").write_text("# T\nbody", encoding="utf-8")
    monkeypatch.chdir(work)
    a = _notes(tmp_path)
    r = a.organize_notes("")
    assert "error" in r
    assert not (tmp_path / "organized").exists()
    r = asyncio.run(a.run({"type": "organize_notes", "params": {"source_dir": ""}}))
    assert r["status"] == "error"


def test_source_dir_file_rejected(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# x", encoding="utf-8")
    assert "error" in _notes(tmp_path).organize_notes(str(f))


def test_duplicate_headings_not_dropped(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("# Same\none", encoding="utf-8")
    (src / "b.md").write_text("# Same\ntwo", encoding="utf-8")
    a = _notes(tmp_path)
    with patch.object(a, "_call_ollama", return_value="tech"):
        r = a.organize_notes(str(src))
    assert r["total_notes"] == 2


def test_summarize_no_match_no_llm_fabrication(tmp_path):
    a = _notes(tmp_path)
    with patch.object(a, "_call_ollama", return_value="invented summary") as llm:
        r = a.summarize_notes("quantum")
    llm.assert_not_called()
    assert r["matching_notes"] == 0 and r["summary"] == ""
    a.memory.store.assert_not_called()
