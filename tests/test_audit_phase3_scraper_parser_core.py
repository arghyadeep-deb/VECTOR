"""Audit phase 3: core/scraper/parser.py + core/scraper/core/* regression tests (no network, storage under tmp_path)."""

import logging

import pytest

pytest.importorskip("lxml")
pytest.importorskip("cssselect")
pytest.importorskip("orjson")
pytest.importorskip("w3lib")

from core.scraper.parser import Selector  # noqa: E402
from core.scraper.core.storage import SQLiteStorageSystem  # noqa: E402
from core.scraper.core.utils import _StorageTools  # noqa: E402


def _adaptive(html, tmp_path, name="s.db", **kw):
    return Selector(
        html,
        adaptive=True,
        storage_args={"storage_file": str(tmp_path / name), "url": "http://example.com/"},
        **kw,
    )


def test_element_path_deep_dom_does_not_hit_recursion_limit():
    depth = 1500  # below libxml2's ~2046 nesting cap, above Python's default recursion limit
    page = Selector("<div>" * depth + "<p>t</p>" + "</div>" * depth)
    target = page.css("p")[0]
    data = _StorageTools.element_to_dict(target._root)
    assert len(data["path"]) == depth + 3  # html, body, depth divs, p
    assert data["path"][-1] == "p"
    assert target.generate_css_selector.endswith("p")


def test_save_element_with_comment_sibling_is_serializable(tmp_path):
    page = _adaptive("<div><!--c--><p class='a'>1</p></div>", tmp_path, keep_comments=True)
    assert len(page.css("p", auto_save=True)) == 1  # old: TypeError "Type is not JSON serializable"
    assert page.retrieve("p")["tag"] == "p"


def test_adaptive_auto_save_without_relocation_returns_empty_not_indexerror(tmp_path):
    first = _adaptive("<div><p class='a'>1</p></div>", tmp_path, "b.db")
    first.css("p", identifier="k", auto_save=True)
    second = _adaptive("<section><span>zzz</span></section>", tmp_path, "b.db")
    # old: relocate() -> [] but `[] is not None` -> elements[0] -> IndexError
    assert list(second.css("p.q", identifier="k", adaptive=True, auto_save=True)) == []


def test_adaptive_lookup_with_unsaved_identifier_warns(tmp_path, caplog):
    page = _adaptive("<div><p>1</p></div>", tmp_path, "c.db")
    with caplog.at_level(logging.WARNING, logger="vector_scraper"):
        assert len(page.css("p.missing", identifier="never-saved", adaptive=True)) == 0
    assert any("never-saved" in r.getMessage() for r in caplog.records)


def test_find_similar_handles_prefixed_tag_names():
    page = Selector("<div><o:p class='a'>1</o:p><o:p class='a'>2</o:p></div>")
    first = page.css("div")[0].children[0]
    assert first.tag == "o:p"
    # old: XPathEvalError "Undefined namespace prefix"
    similar = first.find_similar()
    assert [s.text for s in similar] == ["2"]


def test_find_all_attribute_value_with_backslash():
    page = Selector('<a title="x\\">a</a><a title="y">b</a>')
    found = page.find_all("a", title="x\\")  # old: SelectorSyntaxError (Unclosed string)
    assert [f.text for f in found] == ["a"]


def test_generated_css_selector_with_non_identifier_id_roundtrips():
    page = Selector('<div id="a.b"><p>1</p><div id="c"><p>2</p></div></div>')
    target = page.css("p")[0]
    selector = target.generate_css_selector
    # old: "#a.b > p" (matches id=a class=b -> nothing)
    assert [m.text for m in page.css(selector)] == ["1"]


@pytest.mark.parametrize("ident", ["a'b", 'a"b', "a'b\"c"])
def test_generated_xpath_with_quotes_in_id_roundtrips(ident):
    doc = Selector("<div><p>1</p></div>")
    # build a page whose div id contains quotes via the DOM (attribute escaping handled by lxml)
    doc.css("div")[0]._root.set("id", ident)
    target = doc.css("p")[0]
    for xp in (target.generate_xpath_selector, target.generate_full_xpath_selector):
        assert [m.text for m in doc.xpath(xp)] == ["1"], xp  # old: XPath syntax error


def test_attr_pseudo_element_rejects_xpath_injection():
    page = Selector('<a href="x">1</a><script src="s"></script>')
    assert list(page.css("a::attr(href)")) == ["x"] or [str(m) for m in page.css("a::attr(href)")] == ["x"]
    # old: translated to `/@x|//script/@src` and returned the script's src
    with pytest.raises(Exception) as exc:
        page.css('a::attr("x|//script/@src")')
    assert "attr" in str(exc.value).lower()


def test_storage_close_is_idempotent(tmp_path):
    store = SQLiteStorageSystem(storage_file=str(tmp_path / "idem.db"), url="http://example.com/?token=SECRET")
    store.close()
    store.close()  # old: sqlite3.ProgrammingError (closed database)
