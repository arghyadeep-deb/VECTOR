"""Sub-project D follow-ups: ARM A narrates a real generated script (it used to narrate the bare
topic), and interrupted renders that still exist on disk are reported as resumable."""
from __future__ import annotations

import datetime
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.content import video_pipeline as vp
from districts.growth.content_arm import ContentArm


@pytest.mark.asyncio
async def test_arm_a_script_uses_generated_content():
    gen = AsyncMock(return_value={"content": "INTRO: real generated script", "topic": "t"})
    with patch("districts.content.script_generator.ScriptGenerator.generate_script", new=gen):
        text, well = await ContentArm()._script("work_done")
    assert text == "INTRO: real generated script" and well == "work_done"
    assert gen.await_args.args[0] == "what VECTOR did today"


@pytest.mark.asyncio
async def test_arm_a_script_falls_back_to_brand_line_not_the_bare_topic():
    gen = AsyncMock(return_value={"error": "llm down", "content": ""})
    with patch("districts.content.script_generator.ScriptGenerator.generate_script", new=gen):
        text, _ = await ContentArm()._script("capability_showcase")
    assert "VECTOR" in text and text != "a VECTOR capability showcase"


def _seed(db: Path, jobs: list[tuple]) -> None:
    with sqlite3.connect(str(db)) as c:
        for jid, status, path, age_h in jobs:
            ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_h)).isoformat()
            c.execute(
                "INSERT INTO content_jobs (id, topic, niche, platform, status, stage_pct, created_at, updated_at, video_path)"
                " VALUES (?,?,?,?,?,?,?,?,?)", (jid, "t", "n", "both", status, 85, ts, ts, path))


def test_interrupted_job_with_saved_render_is_listed_resumable(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "_DB_PATH", tmp_path / "cj.db")
    vp._init_db()
    render = tmp_path / "keep.mp4"
    render.write_bytes(b"x")
    _seed(tmp_path / "cj.db", [
        ("with-render", "uploading", str(render), 5),
        ("lost-render", "uploading", str(tmp_path / "gone.mp4"), 5),
        ("fresh", "uploading", str(render), 0),
    ])
    assert vp.recover_interrupted_jobs(max_age_hours=2.0) == 2
    by_id = {j["id"]: j for j in vp.get_job_queue()}
    assert by_id["with-render"]["status"] == "error" and "render saved" in by_id["with-render"]["error"]
    assert "render saved" not in by_id["lost-render"]["error"]
    assert by_id["fresh"]["status"] == "uploading"
    assert [j["id"] for j in vp.list_resumable_jobs()] == ["with-render"]


def test_recover_never_uploads_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "_DB_PATH", tmp_path / "cj.db")
    vp._init_db()
    render = tmp_path / "keep.mp4"
    render.write_bytes(b"x")
    _seed(tmp_path / "cj.db", [("j", "uploading", str(render), 5)])
    with patch.object(vp.VideoPipelineAgent, "_upload_youtube", new=AsyncMock()) as yt, \
         patch.object(vp.VideoPipelineAgent, "_upload_instagram", new=AsyncMock()) as ig:
        vp.recover_interrupted_jobs()
        vp.list_resumable_jobs()
    yt.assert_not_called()
    ig.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
