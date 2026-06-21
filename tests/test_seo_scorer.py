"""Repo integration (docs/repo_analysis/youtube-automation-agent.md): pure
offline SEO scorer + chapter builder — no API calls, no LLM, no deps."""
from districts.content.seo_scorer import score_seo, build_chapters


def test_score_seo_returns_0_to_100():
    result = score_seo("A title", "", [])
    assert 0 <= result["score"] <= 100
    assert set(result["breakdown"].keys()) == {"title", "description", "tags", "format"}


def test_score_seo_empty_inputs_score_low():
    result = score_seo("", "", [])
    assert result["score"] < 20
    assert "title is empty" in result["suggestions"]


def test_score_seo_good_title_scores_higher_than_bad_title():
    good = score_seo("5 Python Tricks Every Beginner Should Know in 2026", "x" * 250, ["python tips", "python basics"])
    bad = score_seo("stuff", "", [])
    assert good["score"] > bad["score"]


def test_score_seo_title_in_sweet_spot_scores_well():
    title = "5 Python Tricks Every Beginner Should Know in 2026"  # 51 chars, has number+year+power word
    result = score_seo(title)
    assert result["breakdown"]["title"] >= 24  # length + number + year + power word


def test_score_seo_title_too_long_flagged():
    result = score_seo("x" * 150)
    assert any("exceeds" in s for s in result["suggestions"])


def test_score_seo_description_with_timestamps_and_link_scores_well():
    desc = "Intro\n\n0:00 Intro\n1:30 Main content\n\nWatch more: https://youtube.com/@vector"
    result = score_seo("title", desc)
    assert result["breakdown"]["description"] >= 22


def test_score_seo_tags_long_tail_detected():
    result = score_seo("title", "", ["python", "python tutorial for beginners"])
    assert result["breakdown"]["tags"] > 0


def test_score_seo_duplicate_tags_penalized():
    with_dupes = score_seo("title", "", ["python", "Python", "python tricks"])
    no_dupes = score_seo("title", "", ["python", "python tricks", "coding"])
    assert with_dupes["breakdown"]["tags"] < no_dupes["breakdown"]["tags"]


def test_build_chapters_empty_returns_empty():
    assert build_chapters([]) == []


def test_build_chapters_first_starts_at_zero():
    chapters = build_chapters([{"name": "intro", "duration_sec": 30}, {"name": "main", "duration_sec": 120}])
    assert chapters[0]["start_sec"] == 0
    assert chapters[0]["label"] == "0:00"


def test_build_chapters_cumulative_timestamps():
    chapters = build_chapters([
        {"name": "intro", "duration_sec": 30},
        {"name": "main", "duration_sec": 120},
        {"name": "outro", "duration_sec": 20},
    ])
    assert [c["start_sec"] for c in chapters] == [0, 30, 150]


def test_build_chapters_enforces_minimum_10s_gap():
    """YouTube requires consecutive chapters to be >=10s apart."""
    chapters = build_chapters([
        {"name": "a", "duration_sec": 2},
        {"name": "b", "duration_sec": 2},
        {"name": "c", "duration_sec": 2},
    ])
    for i in range(1, len(chapters)):
        assert chapters[i]["start_sec"] - chapters[i - 1]["start_sec"] >= 10


def test_build_chapters_uses_title_over_name_when_both_present():
    chapters = build_chapters([{"name": "intro_hook", "title": "Introduction", "duration_sec": 10}])
    assert chapters[0]["title"] == "Introduction"


def test_build_chapters_format_hours_when_long():
    chapters = build_chapters([
        {"name": "a", "duration_sec": 3700},
        {"name": "b", "duration_sec": 10},
    ])
    assert chapters[1]["label"].count(":") == 2  # h:mm:ss
