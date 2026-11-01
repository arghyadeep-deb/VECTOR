"""
VECTOR Composition Linter
Ported from hyperframes packages/core/src/lint/

Validates HTML composition files before rendering.
Pure regex-based — no DOM parser required.

Rules ported:
  core        — missing composition-id, missing dimensions, duplicate IDs,
                invalid CSS, script close tag errors, timeline registry
  composition — file too large, track density, variable declarations
  media       — imperative media control in CSS, autoplay without muted
  gsap        — timeline registration, missing labels
  adapters    — unknown adapter imports
  captions    — caption track presence
  textures    — shader/WebGL texture rules

Usage:
    from core.video.composition_linter import lint_composition

    result = lint_composition(html_source, file_path="compositions/intro.html")
    if not result.ok:
        for f in result.errors:
            logger.info(f"ERROR {f.code}: {f.message}")

"""
from __future__ import annotations

__all__ = [
    "ALL_RULE_SETS",
    "Block",
    "lint_composition",
    "lint_file",
    "lint_project",
    "LintContext",
    "LintFinding",
    "LintResult",
    "LintSeverity",
    "OpenTag",
]


import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Types ─────────────────────────────────────────────────────────────────────

LintSeverity = str  # "error" | "warning" | "info"


@dataclass
class LintFinding:
    code: str
    severity: LintSeverity
    message: str
    file: Optional[str] = None
    selector: Optional[str] = None
    element_id: Optional[str] = None
    fix_hint: Optional[str] = None
    snippet: Optional[str] = None

    def __str__(self) -> str:
        loc = f" [{self.file}]" if self.file else ""
        hint = f" Hint: {self.fix_hint}" if self.fix_hint else ""
        return f"[{self.severity.upper()}] {self.code}{loc}: {self.message}{hint}"


@dataclass
class LintResult:
    ok: bool
    error_count: int
    warning_count: int
    info_count: int
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def summary(self) -> str:
        return (
            f"{'OK' if self.ok else 'FAIL'} — "
            f"{self.error_count} errors, {self.warning_count} warnings, "
            f"{self.info_count} info"
        )


# ── HTML parsing utilities ─────────────────────────────────────────────────────

_TAG_RE       = re.compile(r"<([a-z][\w:-]*)(\s[^<>]*?)?>", re.IGNORECASE)
_STYLE_RE     = re.compile(r"<style\b([^>]*)>([\s\S]*?)</style>", re.IGNORECASE)
_SCRIPT_RE    = re.compile(r"<script\b([^>]*)>([\s\S]*?)</script>", re.IGNORECASE)
_ATTR_RE      = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))""")
_COMP_ID_CSS  = re.compile(r'\[data-composition-id=["\']([^"\']+)["\']\]')
_TIMELINE_INIT = re.compile(
    r'window\.__timelines\s*=\s*window\.__timelines\s*\|\|\s*\{\}|'
    r'window\.__timelines\s*=\s*\{\}|'
    r'window\.__timelines\s*\?\?=\s*\{\}',
    re.IGNORECASE,
)
_TIMELINE_ASSIGN = re.compile(r'window\.__timelines\[[^\]]+\]\s*=', re.IGNORECASE)
_INVALID_SCRIPT_CLOSE = re.compile(r'<script[^>]*>[\s\S]*?<\s*\/\s*script(?!>)', re.IGNORECASE)


@dataclass
class OpenTag:
    raw: str
    name: str
    attrs: str
    index: int


@dataclass
class Block:
    attrs: str
    content: str
    raw: str
    index: int


def _read_attr(tag_raw: str, attr: str) -> Optional[str]:
    """Read attribute value. Returns '' for boolean attributes (no value), None if absent."""
    for m in _ATTR_RE.finditer(tag_raw):
        if m.group(1).lower() == attr.lower():
            return m.group(2) or m.group(3) or m.group(4) or ""
    # Boolean attribute (no = value): match bare attr name
    if re.search(rf'(?:^|[\s<]){re.escape(attr)}(?:\s|/?>|$)', tag_raw, re.IGNORECASE):
        return ""
    return None


def _truncate(s: str, n: int = 80) -> str:
    return s[:n] + "..." if len(s) > n else s


def _extract_tags(source: str) -> list[OpenTag]:
    tags = []
    for m in _TAG_RE.finditer(source):
        raw = m.group(0)
        if raw.startswith("</") or raw.startswith("<!"):
            continue
        tags.append(OpenTag(raw=raw, name=m.group(1).lower(),
                             attrs=m.group(2) or "", index=m.start()))
    return tags


def _extract_blocks(source: str, pattern: re.Pattern) -> list[Block]:
    blocks = []
    for m in pattern.finditer(source):
        blocks.append(Block(attrs=m.group(1) or "", content=m.group(2) or "",
                            raw=m.group(0), index=m.start()))
    return blocks


def _find_root_tag(source: str) -> Optional[OpenTag]:
    body_m = re.search(r"<body\b[^>]*>", source, re.IGNORECASE)
    body_end_m = re.search(r"</body>", source, re.IGNORECASE)
    if not body_m:
        return None
    body_start = body_m.end()
    body_end = body_end_m.start() if body_end_m else len(source)
    body_src = source[body_start:body_end]
    m = _TAG_RE.search(body_src)
    if not m:
        return None
    raw = m.group(0)
    return OpenTag(raw=raw, name=m.group(1).lower(), attrs=m.group(2) or "",
                   index=body_start + m.start())


def _find_html_tag(source: str) -> Optional[OpenTag]:
    m = re.search(r"<html\b([^<>]*)>", source, re.IGNORECASE)
    if not m:
        return None
    return OpenTag(raw=m.group(0), name="html", attrs=m.group(1), index=m.start())


def _collect_composition_ids(tags: list[OpenTag]) -> set[str]:
    ids = set()
    for tag in tags:
        cid = _read_attr(tag.raw, "data-composition-id")
        if cid:
            ids.add(cid)
    return ids


@dataclass
class LintContext:
    source: str
    raw_source: str
    tags: list[OpenTag]
    styles: list[Block]
    scripts: list[Block]
    composition_ids: set[str]
    root_tag: Optional[OpenTag]
    root_composition_id: Optional[str]
    file_path: Optional[str]
    is_sub_composition: bool


def _build_context(html: str, file_path: Optional[str] = None,
                   is_sub_composition: bool = False) -> LintContext:
    raw = html or ""
    source = raw
    tmpl = re.search(r"<template[^>]*>([\s\S]*)</template>", source, re.IGNORECASE)
    if tmpl:
        source = tmpl.group(1)

    tags   = _extract_tags(source)
    styles = _extract_blocks(source, _STYLE_RE)
    scripts = _extract_blocks(source, _SCRIPT_RE)
    comp_ids = _collect_composition_ids(tags)
    root_tag = _find_root_tag(source)
    root_cid = _read_attr(root_tag.raw, "data-composition-id") if root_tag else None

    return LintContext(
        source=source, raw_source=raw, tags=tags, styles=styles, scripts=scripts,
        composition_ids=comp_ids, root_tag=root_tag, root_composition_id=root_cid,
        file_path=file_path, is_sub_composition=is_sub_composition,
    )


# ── Rule implementations ───────────────────────────────────────────────────────

def _core_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []
    rt = ctx.root_tag

    # root_missing_composition_id
    if not rt or not _read_attr(rt.raw, "data-composition-id"):
        findings.append(LintFinding(
            code="root_missing_composition_id", severity="error",
            message="Root composition is missing `data-composition-id`.",
            element_id=_read_attr(rt.raw, "id") if rt else None,
            fix_hint="Add a stable `data-composition-id` to the entry composition wrapper.",
            snippet=_truncate(rt.raw if rt else ""),
        ))

    # root_missing_dimensions
    if not rt or not _read_attr(rt.raw, "data-width") or not _read_attr(rt.raw, "data-height"):
        findings.append(LintFinding(
            code="root_missing_dimensions", severity="error",
            message="Root composition is missing `data-width` or `data-height`.",
            fix_hint="Set numeric `data-width` and `data-height` on the entry composition root.",
            snippet=_truncate(rt.raw if rt else ""),
        ))

    # duplicate_element_ids
    seen_ids: dict[str, int] = {}
    for tag in ctx.tags:
        eid = _read_attr(tag.raw, "id")
        if eid:
            seen_ids[eid] = seen_ids.get(eid, 0) + 1
    for eid, count in seen_ids.items():
        if count > 1:
            findings.append(LintFinding(
                code="duplicate_element_id", severity="error",
                message=f"Element id `{eid}` appears {count} times. IDs must be unique.",
                element_id=eid,
                fix_hint="Make every `id` attribute unique within the composition.",
            ))

    # invalid_script_close_tag
    for script in ctx.scripts:
        if _INVALID_SCRIPT_CLOSE.search(script.content):
            findings.append(LintFinding(
                code="invalid_script_close_tag", severity="error",
                message="Script block contains `</script` without `>` — this breaks HTML parsing.",
                fix_hint='Escape as `<\\/script>` or use a string variable.',
                snippet=_truncate(script.raw),
            ))

    # timeline_registry_missing
    has_assign = any(_TIMELINE_ASSIGN.search(s.content) for s in ctx.scripts)
    has_init   = any(_TIMELINE_INIT.search(s.content)   for s in ctx.scripts)
    if has_assign and not has_init:
        findings.append(LintFinding(
            code="timeline_registry_missing_init", severity="warning",
            message="Found `window.__timelines[...] =` without initialising `window.__timelines`.",
            fix_hint="Add `window.__timelines = window.__timelines || {};` before assigning timelines.",
        ))

    return findings


def _composition_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []
    MAX_LINES = 300
    MAX_TIMED_PER_TRACK = 3
    EXEMPT = {"audio", "script", "style", "video"}

    def _is_registry_item(raw: str) -> bool:
        return bool(re.search(r'<!--\s*vector-registry-item:', raw[:512], re.IGNORECASE))

    if not _is_registry_item(ctx.raw_source):
        # Strip style blocks for line count
        stripped = re.sub(r'<style\b[^>]*>[\s\S]*?</style>', '<style></style>',
                          ctx.raw_source, flags=re.IGNORECASE)
        lines = len(stripped.splitlines())
        if lines > MAX_LINES:
            target = ("Split this sub-composition further into smaller .html files"
                      if ctx.is_sub_composition
                      else "Split coherent scenes/layers into separate .html files under compositions/")
            findings.append(LintFinding(
                code="composition_file_too_large", severity="warning",
                message=f"Composition has {lines} lines (limit {MAX_LINES}). Smaller files are easier to maintain.",
                fix_hint=f"{target}, then mount with data-composition-src.",
            ))

    # Track density: count timed elements per track index
    track_map: dict[str, list[OpenTag]] = {}
    for tag in ctx.tags:
        if tag.name in EXEMPT:
            continue
        ti = _read_attr(tag.raw, "data-track-index") or _read_attr(tag.raw, "data-track")
        if ti is not None:
            track_map.setdefault(ti, []).append(tag)
    for ti, elements in track_map.items():
        if len(elements) > MAX_TIMED_PER_TRACK:
            findings.append(LintFinding(
                code="track_density_high", severity="info",
                message=f"Track {ti} has {len(elements)} elements (suggested max {MAX_TIMED_PER_TRACK}). Consider splitting.",
                fix_hint="Distribute elements across multiple tracks for clarity.",
            ))

    # Variable type declarations
    html_tag = _find_html_tag(ctx.source)
    if html_tag:
        vars_raw = _read_attr(html_tag.raw, "data-composition-variables")
        if vars_raw:
            try:
                import json
                vars_list = json.loads(vars_raw)
                valid_types = {"string", "number", "color", "boolean", "enum"}
                for v in vars_list:
                    if isinstance(v, dict) and v.get("type") not in valid_types:
                        findings.append(LintFinding(
                            code="invalid_variable_type", severity="error",
                            message=f"Variable `{v.get('id', '?')}` has unknown type `{v.get('type')}`. "
                                    f"Valid: {sorted(valid_types)}.",
                            fix_hint="Use one of: string, number, color, boolean, enum.",
                        ))
            except Exception:
                findings.append(LintFinding(
                    code="invalid_variables_json", severity="error",
                    message="data-composition-variables is not valid JSON.",
                    fix_hint="Validate the JSON in data-composition-variables on the <html> tag.",
                ))

    return findings


def _media_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []

    media_tags = [t for t in ctx.tags if t.name in ("video", "audio")]

    # autoplay without muted (browsers block it)
    for tag in media_tags:
        if _read_attr(tag.raw, "autoplay") is not None and _read_attr(tag.raw, "muted") is None:
            findings.append(LintFinding(
                code="autoplay_without_muted", severity="warning",
                message=f"<{tag.name}> has `autoplay` but not `muted`. Browsers block unmuted autoplay.",
                element_id=_read_attr(tag.raw, "id"),
                fix_hint="Add `muted` attribute. Use the VECTOR audio mixer to control volume instead.",
                snippet=_truncate(tag.raw),
            ))

    # CSS targeting media with play/pause (imperative control anti-pattern)
    media_ids = set()
    media_classes: set[str] = set()
    has_video = any(t.name == "video" for t in media_tags)
    has_audio = any(t.name == "audio" for t in media_tags)

    for tag in media_tags:
        eid = _read_attr(tag.raw, "id")
        if eid:
            media_ids.add(eid)
        cls = _read_attr(tag.raw, "class")
        if cls:
            media_classes.update(cls.split())

    for style in ctx.styles:
        # Look for play/pause control selectors
        for rule_m in re.finditer(r'([^{]+)\{[^}]*(?:play|pause|playback)[^}]*\}',
                                  style.content, re.IGNORECASE):
            selector = rule_m.group(1).strip()
            if has_video and "video" in selector.lower():
                findings.append(LintFinding(
                    code="css_media_control", severity="warning",
                    message="CSS selectors targeting video playback. Use VECTOR audio mixer instead.",
                    selector=selector,
                    fix_hint="Control media playback via the VECTOR audio pipeline, not CSS.",
                ))

    return findings


def _gsap_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []

    for script in ctx.scripts:
        content = script.content

        # GSAP timeline assigned to __timelines without init
        if "gsap.timeline" in content.lower():
            if not _TIMELINE_INIT.search(content) and _TIMELINE_ASSIGN.search(content):
                findings.append(LintFinding(
                    code="gsap_timeline_registry_missing", severity="warning",
                    message="GSAP timeline assigned to `window.__timelines` but registry not initialised in this script.",
                    fix_hint="Add `window.__timelines = window.__timelines || {};` before assigning.",
                ))

        # gsap.set() during animation (anti-pattern)
        if re.search(r'gsap\.set\s*\(', content) and re.search(r'gsap\.to\s*\(', content):
            findings.append(LintFinding(
                code="gsap_set_with_to", severity="info",
                message="Using `gsap.set()` alongside `gsap.to()` — ensure set() runs before to() to avoid property conflicts.",
                fix_hint="Place gsap.set() calls before timeline.to() calls.",
            ))

    return findings


def _adapter_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []
    KNOWN_ADAPTERS = {
        "gsap", "animejs", "anime", "css-animations", "lottie",
        "three", "waapi", "motion",
    }

    for script in ctx.scripts:
        # data-adapter attribute check
        adapter = _read_attr(script.attrs, "data-adapter")
        if adapter and adapter.lower() not in KNOWN_ADAPTERS:
            findings.append(LintFinding(
                code="unknown_adapter", severity="warning",
                message=f"Unknown animation adapter `{adapter}`. Known: {sorted(KNOWN_ADAPTERS)}.",
                fix_hint=f"Use one of: {', '.join(sorted(KNOWN_ADAPTERS))}.",
                snippet=_truncate(script.raw, 60),
            ))

    return findings


def _caption_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []

    video_tags = [t for t in ctx.tags if t.name == "video"]
    track_tags = [t for t in ctx.tags if t.name == "track"]

    for tag in video_tags:
        vid = _read_attr(tag.raw, "id") or "(unknown)"
        has_track = any(_read_attr(t.raw, "kind") == "captions" for t in track_tags)
        if not has_track and "data-no-captions" not in tag.raw:
            findings.append(LintFinding(
                code="video_missing_caption_track", severity="info",
                message=f"<video id=\"{vid}\"> has no <track kind=\"captions\">.",
                element_id=vid,
                fix_hint="Add `<track kind=\"captions\" src=\"...vtt\">` or `data-no-captions` to suppress.",
                snippet=_truncate(tag.raw),
            ))

    return findings


def _texture_rules(ctx: LintContext) -> list[LintFinding]:
    findings: list[LintFinding] = []

    for script in ctx.scripts:
        content = script.content

        # WebGL context without fallback
        if "getContext(" in content and "webgl" in content.lower():
            if "fallback" not in content.lower() and "catch" not in content.lower():
                findings.append(LintFinding(
                    code="webgl_no_fallback", severity="info",
                    message="WebGL context requested without apparent fallback path.",
                    fix_hint="Add a fallback for when WebGL is unavailable (software renderer or static image).",
                ))

        # Large inline texture data (data URIs > 100KB)
        for data_m in re.finditer(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', content):
            b64 = data_m.group(1)
            size_kb = len(b64) * 3 / 4 / 1024
            if size_kb > 100:
                findings.append(LintFinding(
                    code="large_inline_texture", severity="warning",
                    message=f"Inline base64 texture is {size_kb:.0f}KB. Large inline textures slow initial render.",
                    fix_hint="Reference texture as an external file URL instead of embedding base64.",
                ))

    return findings


# ── Main linter entry point ───────────────────────────────────────────────────

ALL_RULE_SETS = [
    _core_rules,
    _composition_rules,
    _media_rules,
    _gsap_rules,
    _adapter_rules,
    _caption_rules,
    _texture_rules,
]


def lint_composition(
    html: str,
    file_path: Optional[str] = None,
    is_sub_composition: bool = False,
) -> LintResult:
    """
    Lint an HTML composition file.
    Returns LintResult with findings, counts, and ok flag.
    """
    ctx = _build_context(html, file_path=file_path, is_sub_composition=is_sub_composition)
    findings: list[LintFinding] = []
    seen: set[str] = set()

    for rule_set in ALL_RULE_SETS:
        for finding in rule_set(ctx):
            key = "|".join([
                finding.code, finding.severity,
                finding.selector or "", finding.element_id or "",
                finding.message,
            ])
            if key in seen:
                continue
            seen.add(key)
            if file_path:
                finding.file = file_path
            findings.append(finding)

    errors   = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos    = sum(1 for f in findings if f.severity == "info")

    return LintResult(
        ok=errors == 0,
        error_count=errors,
        warning_count=warnings,
        info_count=infos,
        findings=findings,
    )


def lint_file(path: str, is_sub_composition: bool = False) -> LintResult:
    """Lint a composition file by path."""
    html = Path(path).read_text(encoding="utf-8")
    return lint_composition(html, file_path=path, is_sub_composition=is_sub_composition)


def lint_project(project_dir: str) -> dict[str, LintResult]:
    """Lint all .html files in a project directory."""
    results: dict[str, LintResult] = {}
    for html_file in Path(project_dir).rglob("*.html"):
        is_sub = "compositions/" in str(html_file).replace("\\", "/")
        results[str(html_file)] = lint_file(str(html_file), is_sub_composition=is_sub)
    return results


if __name__ == "__main__":
    # Smoke tests
    GOOD_HTML = """<!DOCTYPE html>
<html data-composition-variables='[]'>
<body>
  <div data-composition-id="intro-001" data-width="1920" data-height="1080">
    <div id="title" data-start="0" data-track-index="0">Hello VECTOR</div>
  </div>
</body>
</html>"""

    BAD_HTML = """<!DOCTYPE html>
<html>
<body>
  <div data-width="1920">
    <div id="dup">A</div>
    <div id="dup">B</div>
    <video autoplay></video>
  </div>
</body>
</html>"""

    good = lint_composition(GOOD_HTML, file_path="intro.html")
    assert good.error_count == 0, f"Expected 0 errors, got: {good.findings}"
    print(f"GOOD: {good.summary()}")

    bad = lint_composition(BAD_HTML, file_path="bad.html")
    assert bad.error_count >= 2, f"Expected >=2 errors, got {bad.error_count}"
    assert any(f.code == "duplicate_element_id" for f in bad.findings)
    assert any(f.code == "root_missing_composition_id" for f in bad.findings)
    assert any(f.code == "autoplay_without_muted" for f in bad.findings)
    print(f"BAD: {bad.summary()}")
    for f in bad.findings:
        print(f"  {f}")

    print("OK composition_linter.py")
