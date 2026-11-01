
import re
import math
import asyncio
import datetime
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

class AccessibilityAuditor(AgentBase):
    """
    WCAG 2.2 AA compliance auditor for VECTOR's HTML/UI outputs.
    Tests keyboard navigation, ARIA attributes, color contrast,
    heading hierarchy, form labels, and screen reader compatibility.
    RULE 11: local models only — never Claude API at runtime.
    """

    WCAG_CRITERIA = {
        "1.1.1": "Non-text Content — provide alt text",
        "1.3.1": "Info and Relationships — semantic structure",
        "1.3.2": "Meaningful Sequence — heading hierarchy",
        "1.4.3": "Contrast (Minimum) — 4.5:1 AA, 3:1 for large text",
        "1.4.6": "Contrast (Enhanced) — 7:1 AAA",
        "2.1.1": "Keyboard — all functionality via keyboard",
        "2.4.3": "Focus Order — logical focus sequence",
        "2.4.7": "Focus Visible — visible focus indicator",
        "2.4.11": "Focus Not Obscured (Minimum) — WCAG 2.2",
        "4.1.2": "Name, Role, Value — ARIA labels on interactive elements",
    }

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="AccessibilityAuditor",
            district="qa",
            generation=generation,
        )
        self.capabilities = ["a11y", "accessibility", "aria_fix", "audit", "contrast", "keyboard", "qa"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info(f"[VECTOR][accessibility_auditor] initialized gen={generation}")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ── Core audit methods ────────────────────────────────────────────────────

    def audit_html(self, html_content: str) -> dict:
        """
        Full WCAG 2.2 AA audit on HTML content.
        Returns {issues: [{severity, element, wcag_criterion, fix}], score: 0-100}.
        """
        issues: list[dict] = []

        # 1.1.1 — Missing alt on <img> tags
        imgs = re.findall(r"<img[^>]*>", html_content, re.IGNORECASE)
        for img in imgs:
            if "alt=" not in img.lower():
                issues.append({
                    "severity": "critical",
                    "element": img[:80],
                    "wcag_criterion": "1.1.1",
                    "fix": "Add alt attribute: alt='descriptive text' or alt='' for decorative images",
                })
            elif re.search(r'alt\s*=\s*["\']image["\']', img, re.IGNORECASE):
                issues.append({
                    "severity": "warning",
                    "element": img[:80],
                    "wcag_criterion": "1.1.1",
                    "fix": "Replace generic alt='image' with meaningful description",
                })

        # 4.1.2 — Interactive elements missing aria-label
        interactive_tags = re.findall(
            r"<(button|a|input|select|textarea)[^>]*>",
            html_content, re.IGNORECASE
        )
        for tag in interactive_tags:
            tag_lower = tag.lower()
            has_label = (
                "aria-label" in tag_lower
                or "aria-labelledby" in tag_lower
                or "title=" in tag_lower
                or (re.search(r"<input", tag_lower) and "id=" in tag_lower)
            )
            if not has_label:
                issues.append({
                    "severity": "serious",
                    "element": tag[:80],
                    "wcag_criterion": "4.1.2",
                    "fix": "Add aria-label='...' or aria-labelledby referencing a visible label element",
                })

        # 1.3.2 — Heading hierarchy check (h1 → h2 → h3 must not skip)
        headings = re.findall(r"<h([1-6])[^>]*>", html_content, re.IGNORECASE)
        heading_levels = [int(h) for h in headings]
        for i in range(1, len(heading_levels)):
            if heading_levels[i] > heading_levels[i - 1] + 1:
                issues.append({
                    "severity": "serious",
                    "element": f"h{heading_levels[i-1]} followed by h{heading_levels[i]}",
                    "wcag_criterion": "1.3.2",
                    "fix": f"Don't skip heading levels — use h{heading_levels[i-1] + 1} instead of h{heading_levels[i]}",
                })

        if headings and heading_levels[0] != 1:
            issues.append({
                "severity": "serious",
                "element": f"First heading is h{heading_levels[0]}",
                "wcag_criterion": "1.3.2",
                "fix": "Page should start with exactly one <h1> element",
            })

        # 1.3.1 — Form inputs without <label> or aria-label
        inputs = re.findall(r"<input[^>]*>", html_content, re.IGNORECASE)
        for inp in inputs:
            inp_lower = inp.lower()
            if 'type="hidden"' in inp_lower or "type='hidden'" in inp_lower:
                continue
            if "aria-label" not in inp_lower and "aria-labelledby" not in inp_lower:
                inp_id = re.search(r'id\s*=\s*["\']([^"\']+)["\']', inp, re.IGNORECASE)
                if inp_id:
                    label_for = f'for="{inp_id.group(1)}"'
                    if label_for not in html_content:
                        issues.append({
                            "severity": "serious",
                            "element": inp[:80],
                            "wcag_criterion": "1.3.1",
                            "fix": f"Add <label for='{inp_id.group(1)}'>Label text</label> before the input",
                        })
                else:
                    issues.append({
                        "severity": "critical",
                        "element": inp[:80],
                        "wcag_criterion": "1.3.1",
                        "fix": "Add an id to the input and a matching <label for='id'> element, or use aria-label",
                    })

        # 1.4.3 — Detect likely low-contrast hardcoded color patterns
        low_contrast_patterns = [
            (r"color\s*:\s*#[cC][cC][cC].*background.*#[fF][fF][fF]", "light gray on white"),
            (r"color\s*:\s*#[dD][dD][dD]", "very light text (potential low contrast)"),
            (r"color\s*:\s*#[eE][eE][eE]", "near-white text (likely insufficient contrast)"),
            (r"color\s*:\s*#[aA]{3}", "light gray text on white (ratio likely < 3:1)"),
            (r"color\s*:\s*yellow", "yellow on white (ratio ~1.07:1, fails AA)"),
        ]
        for pattern, description in low_contrast_patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                issues.append({
                    "severity": "serious",
                    "element": f"Inline style: {description}",
                    "wcag_criterion": "1.4.3",
                    "fix": "Ensure contrast ratio >= 4.5:1 for normal text, >= 3:1 for large text (18pt+)",
                })

        # Score: start at 100, deduct per issue
        severity_penalties = {"critical": 15, "serious": 10, "warning": 5, "info": 2}
        penalty = sum(severity_penalties.get(issue["severity"], 5) for issue in issues)
        score = max(0, 100 - penalty)

        result = {"issues": issues, "score": score, "total_issues": len(issues)}
        logger.info(f"[VECTOR][accessibility_auditor] audit: {len(issues)} issues, score={score}")
        return result

    def check_keyboard_navigation(self, html_content: str) -> dict:
        """
        Finds elements needing tabindex, focus indicators, and skip links.
        Returns {findings: list[dict], has_skip_link: bool, focusable_count: int}.
        """
        findings: list[dict] = []

        # Skip link check
        has_skip_link = bool(re.search(
            r'href\s*=\s*["\']#(main|content|maincontent|skip)["\']',
            html_content, re.IGNORECASE
        ))
        if not has_skip_link:
            findings.append({
                "issue": "Missing skip navigation link",
                "wcag_criterion": "2.4.1",
                "fix": "Add <a href='#main-content' class='skip-link'>Skip to main content</a> as first focusable element",
            })

        # tabindex=-1 on non-interactive elements (pulls them from tab order)
        bad_tabindex = re.findall(
            r"<(?!input|button|a|select|textarea)\w+[^>]*tabindex\s*=\s*[\"']-1[\"'][^>]*>",
            html_content, re.IGNORECASE
        )
        for el in bad_tabindex:
            findings.append({
                "issue": f"tabindex=-1 on non-interactive element removes it from focus order",
                "element": el[:80],
                "wcag_criterion": "2.1.1",
                "fix": "Only use tabindex=-1 on elements you control focus to programmatically (e.g., modals)",
            })

        # tabindex > 0 anti-pattern
        positive_tabindex = re.findall(r"tabindex\s*=\s*[\"']?([1-9]\d*)[\"']?", html_content, re.IGNORECASE)
        for val in positive_tabindex:
            findings.append({
                "issue": f"tabindex={val} creates unpredictable focus order",
                "wcag_criterion": "2.4.3",
                "fix": "Use tabindex='0' to add to natural flow; never use positive tabindex values",
            })

        # Missing :focus style
        has_focus_style = ":focus" in html_content or "outline:" in html_content
        if not has_focus_style:
            findings.append({
                "issue": "No :focus styles detected in HTML/inline CSS",
                "wcag_criterion": "2.4.7",
                "fix": "Add :focus { outline: 2px solid #005fcc; outline-offset: 2px; } in your stylesheet",
            })

        # Outline:none / outline:0 anti-pattern
        outline_removed = re.findall(r"outline\s*:\s*0|outline\s*:\s*none", html_content, re.IGNORECASE)
        if outline_removed:
            findings.append({
                "issue": f"outline:none/0 removes visible focus indicator ({len(outline_removed)} occurrence(s))",
                "wcag_criterion": "2.4.11",
                "fix": "Never suppress focus outlines without providing an equivalent custom focus style",
            })

        # Count focusable elements
        focusable_count = len(re.findall(
            r"<(a\s|button|input|select|textarea)[^>]*>",
            html_content, re.IGNORECASE
        ))

        return {
            "findings": findings,
            "has_skip_link": has_skip_link,
            "focusable_count": focusable_count,
            "keyboard_issues": len(findings),
        }

    def generate_aria_fixes(self, html_content: str) -> str:
        """
        Returns improved HTML with ARIA roles/labels added to common patterns.
        """
        fixed = html_content

        # Add role="navigation" to <nav> if missing
        fixed = re.sub(
            r"<nav(?![^>]*role=)",
            '<nav role="navigation"',
            fixed, flags=re.IGNORECASE
        )

        # Add role="main" to <main> if missing
        fixed = re.sub(
            r"<main(?![^>]*role=)",
            '<main role="main"',
            fixed, flags=re.IGNORECASE
        )

        # Add role="banner" to <header> if missing
        fixed = re.sub(
            r"<header(?![^>]*role=)",
            '<header role="banner"',
            fixed, flags=re.IGNORECASE
        )

        # Add role="contentinfo" to <footer> if missing
        fixed = re.sub(
            r"<footer(?![^>]*role=)",
            '<footer role="contentinfo"',
            fixed, flags=re.IGNORECASE
        )

        # Add aria-label to <button> without any label
        def add_button_label(m: re.Match) -> str:
            tag = m.group(0)
            if "aria-label" not in tag.lower() and "aria-labelledby" not in tag.lower():
                return tag.rstrip(">") + ' aria-label="button">'
            return tag

        fixed = re.sub(r"<button[^>]*>", add_button_label, fixed, flags=re.IGNORECASE)

        # Add alt="" to decorative images that have no alt
        def add_decorative_alt(m: re.Match) -> str:
            tag = m.group(0)
            if "alt=" not in tag.lower():
                return tag.rstrip(">") + ' alt="">'
            return tag

        fixed = re.sub(r"<img[^>]*>", add_decorative_alt, fixed, flags=re.IGNORECASE)

        logger.info("[VECTOR][accessibility_auditor] ARIA fixes applied")
        return fixed

    def audit_color_contrast(self, foreground_hex: str, background_hex: str) -> dict:
        """
        Calculates WCAG contrast ratio using relative luminance formula.
        Returns {ratio, aa_pass, aaa_pass, recommendation}.
        """
        def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join(c * 2 for c in hex_color)
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return r, g, b

        def _relative_luminance(r: int, g: int, b: int) -> float:
            """WCAG 2.x relative luminance formula."""
            def _linearize(v: float) -> float:
                v /= 255.0
                return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

            return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)

        try:
            fg_r, fg_g, fg_b = _hex_to_rgb(foreground_hex)
            bg_r, bg_g, bg_b = _hex_to_rgb(background_hex)
        except Exception as e:
            return {"error": f"Invalid hex color: {e}", "ratio": 0.0, "aa_pass": False, "aaa_pass": False}

        lum_fg = _relative_luminance(fg_r, fg_g, fg_b)
        lum_bg = _relative_luminance(bg_r, bg_g, bg_b)

        lighter = max(lum_fg, lum_bg)
        darker = min(lum_fg, lum_bg)
        ratio = (lighter + 0.05) / (darker + 0.05)
        ratio = round(ratio, 2)

        aa_normal = ratio >= 4.5
        aa_large = ratio >= 3.0
        aaa_normal = ratio >= 7.0
        aaa_large = ratio >= 4.5

        if ratio >= 7.0:
            recommendation = "Excellent — passes WCAG AAA for all text sizes"
        elif ratio >= 4.5:
            recommendation = "Good — passes WCAG AA for normal text and AAA for large text (18pt+/14pt bold+)"
        elif ratio >= 3.0:
            recommendation = "Partial — passes WCAG AA for large text only; increase contrast for normal text"
        else:
            recommendation = f"Fail — ratio {ratio}:1 is below the minimum 3:1 threshold. Darken text or lighten background."

        logger.info(f"[VECTOR][accessibility_auditor] contrast {foreground_hex}/{background_hex}: {ratio}:1 aa={aa_normal}")
        return {
            "ratio": ratio,
            "ratio_string": f"{ratio}:1",
            "aa_normal_text": aa_normal,
            "aa_large_text": aa_large,
            "aaa_normal_text": aaa_normal,
            "aaa_large_text": aaa_large,
            "aa_pass": aa_normal,
            "aaa_pass": aaa_normal,
            "recommendation": recommendation,
        }

    # ── run dispatch ──────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "audit")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "audit":
                html = task.get("html", "")
                result = self.audit_html(html)
                self._get_memory().store(
                    event_type="accessibility_audit",
                    content=f"WCAG audit: {result['total_issues']} issues, score={result['score']}",
                    tags=["qa", "accessibility", "wcag"],
                    source="accessibility_auditor",
                )
                self.award_points(30, "audit_done")
                return {"status": "ok", "result": result}

            elif task_type == "keyboard":
                html = task.get("html", "")
                result = self.check_keyboard_navigation(html)
                self.award_points(20, "keyboard_check_done")
                return {"status": "ok", "result": result}

            elif task_type == "aria_fix":
                html = task.get("html", "")
                fixed_html = self.generate_aria_fixes(html)
                self.award_points(20, "aria_fix_done")
                return {"status": "ok", "fixed_html": fixed_html}

            elif task_type == "contrast":
                fg = task.get("foreground", task.get("fg", "#000000"))
                bg = task.get("background", task.get("bg", "#ffffff"))
                result = self.audit_color_contrast(fg, bg)
                self.award_points(10, "contrast_check_done")
                return {"status": "ok", "result": result}

            else:
                logger.warning(f"[VECTOR][accessibility_auditor] unknown task type: {task_type}")
                result = self.audit_html(task.get("html", ""))
                self.award_points(30, "audit_done")
                return {"status": "ok", "result": result}

        except Exception as e:
            logger.error("[VECTOR][accessibility_auditor] {}", e)
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = AccessibilityAuditor()

        # Test audit_html
        sample_html = """
        <html>
        <body>
          <h1>Title</h1>
          <h3>Skipped heading</h3>
          <img src="logo.png">
          <button>Click</button>
          <input type="text" id="name">
        </body>
        </html>
        """
        audit_result = agent.audit_html(sample_html)
        assert "issues" in audit_result and "score" in audit_result
        assert audit_result["score"] >= 0 and audit_result["score"] <= 100
        print(f"  audit_html: {audit_result['total_issues']} issues, score={audit_result['score']}")

        # Test check_keyboard_navigation
        kb_result = agent.check_keyboard_navigation(sample_html)
        assert "findings" in kb_result and "focusable_count" in kb_result
        print(f"  keyboard_navigation: {kb_result['keyboard_issues']} issues, focusable={kb_result['focusable_count']}")

        # Test generate_aria_fixes
        fixed = agent.generate_aria_fixes("<nav><main><footer><button>Go</button></main></footer></nav>")
        assert 'role="navigation"' in fixed
        assert 'role="main"' in fixed
        print(f"  aria_fix: roles injected OK")

        # Test audit_color_contrast
        contrast = agent.audit_color_contrast("#000000", "#ffffff")
        assert contrast["ratio"] >= 21.0  # black on white
        assert contrast["aa_pass"] is True
        assert contrast["aaa_pass"] is True
        print(f"  contrast #000/#fff: {contrast['ratio_string']}")

        # Test run dispatch
        result = await agent.run({"type": "audit", "html": sample_html})
        assert result["status"] == "ok"
        print(f"[OK] status={result['status']}")
        print("accessibility_auditor.py OK")

    asyncio.run(_smoke())
