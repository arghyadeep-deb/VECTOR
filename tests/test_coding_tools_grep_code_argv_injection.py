"""Regression: districts/coding/coding_tools.py's grep_code() passed
pattern/path straight into `rg` as bare positional args -- a leading '-'
would be read as an rg option instead of the search term (e.g. "--pre=<cmd>"
runs an arbitrary command per file, a real RCE vector). The one external
caller (core/mcp_tools/expansion_modules/files.py's file_grep) already
guarded its own pattern argument this way, but grep_code() itself had no
guard -- fixed at the primitive level (reject + "--" separator) so every
caller is covered, not just that one MCP wrapper.
"""
from districts.coding.coding_tools import grep_code


def test_dash_prefixed_pattern_rejected():
    result = grep_code("--pre=touch /tmp/pwned", path=".")
    assert result["count"] == 0
    assert "error" in result


def test_dash_prefixed_path_rejected():
    result = grep_code("def ", path="--pre=touch /tmp/pwned")
    assert result["count"] == 0
    assert "error" in result


def test_normal_pattern_still_works():
    result = grep_code("class EntityMatcher", path="districts/home_assistant")
    assert result["count"] >= 1
    assert any("entity_manager.py" in m["file"] for m in result["matches"])


if __name__ == "__main__":
    test_dash_prefixed_pattern_rejected()
    test_dash_prefixed_path_rejected()
    test_normal_pattern_still_works()
    print("OK test_coding_tools_grep_code_argv_injection.py")
