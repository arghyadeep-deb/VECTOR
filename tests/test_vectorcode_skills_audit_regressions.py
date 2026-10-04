from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from loguru import logger


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "vectorcode" / "src" / "skills"


def _load_canvas_module():
    path = SKILLS / "optional" / "productivity" / "canvas" / "scripts" / "canvas_api.py"
    spec = importlib.util.spec_from_file_location("canvas_api_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_telephony_module():
    path = SKILLS / "optional" / "productivity" / "telephony" / "scripts" / "telephony.py"
    spec = importlib.util.spec_from_file_location("telephony_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_canvas_pagination_uses_httpx_and_follows_next_link(monkeypatch):
    canvas = _load_canvas_module()
    calls = []

    class Response:
        def __init__(self, payload, link=""):
            self._payload = payload
            self.headers = {"Link": link}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    responses = iter(
        [
            Response([{"id": 1}], '<https://canvas.test/page2>; rel="next"'),
            Response([{"id": 2}]),
        ]
    )

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr(canvas.httpx, "get", fake_get)
    assert canvas._paginated_get("https://canvas.test/page1", {"per_page": 1}) == [
        {"id": 1},
        {"id": 2},
    ]
    assert calls[0][1]["params"] == {"per_page": 1}
    assert calls[1][0] == "https://canvas.test/page2"
    assert calls[1][1]["params"] is None


def test_parser_warning_interpolates_unmapped_field():
    from vectorcode.src.skills.parser import SkillParser

    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        manifest = SkillParser().parse_frontmatter(
            {"name": "demo", "description": "demo skill", "mystery": 7}
        )
    finally:
        logger.remove(sink)

    assert manifest.metadata["vector"]["original_frontmatter"] == {"mystery": 7}
    assert any("'mystery' in skill 'demo'" in message for message in messages)
    assert not any("%s" in message for message in messages)


def test_telephony_corrupt_existing_state_fails_closed(tmp_path):
    telephony = _load_telephony_module()
    state_path = tmp_path / "telephony_state.json"
    state_path.write_text('{"owned_numbers":', encoding="utf-8")

    try:
        telephony._load_state(state_path)
    except telephony.TelephonyError as exc:
        assert "refusing to replace it" in str(exc)
    else:
        raise AssertionError("corrupt persistent telephony state was treated as empty")

    assert state_path.read_text(encoding="utf-8") == '{"owned_numbers":'


def test_touched_loguru_calls_do_not_use_stdlib_formatting():
    relative_paths = [
        "hub.py",
        "loader.py",
        "manager.py",
        "matcher.py",
        "parser.py",
        "optional/productivity/memento-flashcards/scripts/memento_cards.py",
        "optional/productivity/telephony/scripts/telephony.py",
        "optional/research/domain-intel/scripts/domain_intel.py",
        "productivity/google-workspace/scripts/setup.py",
        "productivity/powerpoint/scripts/clean.py",
    ]
    for relative_path in relative_paths:
        path = SKILLS / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not node.args or node.func.attr not in {
                "trace", "debug", "info", "success", "warning", "error",
                "critical", "exception", "log",
            }:
                continue
            message = node.args[0]
            if isinstance(message, ast.Constant) and isinstance(message.value, str):
                assert not any(token in message.value for token in ("%s", "%r", "%d")), (
                    path,
                    node.lineno,
                )
            assert not any(keyword.arg == "exc_info" for keyword in node.keywords), (
                path,
                node.lineno,
            )
