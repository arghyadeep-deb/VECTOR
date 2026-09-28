"""
UI Designer — design tokens, component specs, visual design systems for VECTOR's dashboard.

Generates CSS/design systems, component library specs, dark-mode tokens,
and pixel-perfect UI specifications for VECTOR's monitoring dashboard and outputs.
"""

import asyncio
import json
import re
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

# Design corpus — lazy-loaded on first call
_corpus_search = None

def _get_corpus_search():
    """Lazy import to avoid circular imports and missing-file errors at startup."""
    global _corpus_search
    if _corpus_search is None:
        try:
            from districts.design.knowledge import search_design_corpus
            _corpus_search = search_design_corpus
        except Exception as e:
            logger.debug(f"[VECTOR][ui_designer] corpus unavailable: {e}")
            _corpus_search = lambda q, **kw: []  # noqa: E731
    return _corpus_search

_VECTOR_DESIGN_TOKENS = {
    "colors": {
        "primary": "#6366f1",      # indigo
        "secondary": "#22d3ee",    # cyan
        "success": "#4ade80",      # green
        "warning": "#facc15",      # yellow
        "danger": "#f87171",       # red
        "bg_dark": "#0f172a",      # slate-900
        "bg_surface": "#1e293b",   # slate-800
        "bg_card": "#334155",      # slate-700
        "text_primary": "#f1f5f9", # slate-100
        "text_muted": "#94a3b8",   # slate-400
    },
    "typography": {
        "font_mono": "'JetBrains Mono', 'Fira Code', monospace",
        "font_sans": "'Inter', system-ui, sans-serif",
        "size_xs": "0.75rem", "size_sm": "0.875rem",
        "size_base": "1rem", "size_lg": "1.125rem",
        "size_xl": "1.25rem", "size_2xl": "1.5rem",
    },
    "spacing": {"1": "0.25rem", "2": "0.5rem", "3": "0.75rem", "4": "1rem",
                "6": "1.5rem", "8": "2rem", "12": "3rem"},
    "radius": {"sm": "0.25rem", "md": "0.5rem", "lg": "0.75rem", "full": "9999px"},
    "shadow": {"card": "0 4px 6px -1px rgba(0,0,0,0.4)", "glow": "0 0 20px rgba(99,102,241,0.3)"},
}

class UIDesigner(AgentBase):
    """
    Visual design system specialist. Generates design tokens, component specs,
    CSS variables, dark-mode systems for VECTOR's dashboard and UI outputs.
    """

    def __init__(self):
        super().__init__(agent_id="ui_designer_001", name="UIDesigner", district="design")
        self.capabilities = ["audit", "component", "css_variables", "dashboard", "design", "interface", "search_corpus", "ui"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][ui_designer] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float) -> str:
        """Call the routed model with mandatory session hydration."""
        hydration = ContextEngine().session_hydration_prompt({"query": prompt})
        return chat(
            model=self._model,
            messages=[{"role": "user", "content": f"{hydration}\n\n{prompt}"}],
            timeout=timeout,
            district="design",
            domain="vision",
        )

    def generate_css_variables(self) -> str:
        """Generate CSS custom properties from VECTOR design tokens."""
        tokens = _VECTOR_DESIGN_TOKENS
        lines = [":root {", "  /* VECTOR Design System */"]
        for color_name, value in tokens["colors"].items():
            lines.append(f"  --color-{color_name.replace('_', '-')}: {value};")
        for size_name, value in tokens["typography"].items():
            if size_name.startswith("font"):
                lines.append(f"  --{size_name.replace('_', '-')}: {value};")
            elif size_name.startswith("size"):
                lines.append(f"  --text-{size_name.replace('size_', '')}: {value};")
        for space_name, value in tokens["spacing"].items():
            lines.append(f"  --space-{space_name}: {value};")
        for r_name, value in tokens["radius"].items():
            lines.append(f"  --radius-{r_name}: {value};")
        lines.append("}")
        return "\n".join(lines)

    def spec_component(self, component_name: str, props: list[str] = None) -> dict:
        """Generate a component specification with props, states, accessibility."""
        props = props or ["variant", "size", "disabled", "loading"]
        base_styles = {
            "button": {"padding": "var(--space-2) var(--space-4)", "border-radius": "var(--radius-md)",
                       "font-family": "var(--font-sans)", "cursor": "pointer"},
            "card": {"background": "var(--color-bg-card)", "border-radius": "var(--radius-lg)",
                     "padding": "var(--space-6)", "box-shadow": "var(--shadow-card)"},
            "input": {"background": "var(--color-bg-surface)", "border": "1px solid var(--color-bg-card)",
                      "padding": "var(--space-2) var(--space-3)", "border-radius": "var(--radius-md)",
                      "color": "var(--color-text-primary)"},
            "badge": {"padding": "2px var(--space-2)", "border-radius": "var(--radius-full)",
                      "font-size": "var(--text-xs)", "font-weight": "600"},
        }
        return {
            "component": component_name,
            "props": props,
            "states": ["default", "hover", "active", "disabled", "loading", "focus"],
            "variants": ["primary", "secondary", "danger", "ghost"],
            "sizes": ["sm", "md", "lg"],
            "base_styles": base_styles.get(component_name.lower(), {"display": "block"}),
            "accessibility": {
                "aria_attributes": ["aria-label", "role", "aria-disabled"],
                "focus_visible": "outline: 2px solid var(--color-primary); outline-offset: 2px",
                "wcag_level": "AA",
            },
        }

    def generate_dashboard_layout(self, sections: list[str] = None) -> str:
        """Generate HTML/CSS skeleton for VECTOR monitoring dashboard."""
        sections = sections or ["header", "agent-grid", "memory-feed", "metrics", "console"]
        sections_html = "".join(
            '      <section class="card" id="{0}" aria-label="{1}"></section>\n'.format(
                s, s.replace("-", " ").title()
            )
            for s in sections
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VECTOR Dashboard</title>
  <style>
    {self.generate_css_variables()}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--color-bg-dark); color: var(--color-text-primary);
            font-family: var(--font-sans); min-height: 100vh; }}
    .dashboard {{ display: grid; grid-template-rows: 56px 1fr;
                  grid-template-columns: 240px 1fr; height: 100vh; }}
    .header {{ grid-column: 1/-1; background: var(--color-bg-surface);
               border-bottom: 1px solid var(--color-bg-card);
               display: flex; align-items: center; padding: 0 var(--space-6);
               font-size: var(--text-lg); font-weight: 600; }}
    .sidebar {{ background: var(--color-bg-surface);
                border-right: 1px solid var(--color-bg-card); overflow-y: auto; }}
    .main {{ overflow-y: auto; padding: var(--space-6);
             display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
             gap: var(--space-4); align-content: start; }}
    .card {{ background: var(--color-bg-card); border-radius: var(--radius-lg);
             padding: var(--space-6); box-shadow: var(--shadow-card); }}
    .badge {{ display: inline-flex; align-items: center; padding: 2px var(--space-2);
              border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: 600; }}
    .badge-success {{ background: rgba(74,222,128,0.15); color: var(--color-success); }}
    .badge-danger {{ background: rgba(248,113,113,0.15); color: var(--color-danger); }}
  </style>
</head>
<body>
  <div class="dashboard">
    <header class="header">⚡ VECTOR City Monitor</header>
    <nav class="sidebar" aria-label="Districts">
      <!-- district navigation auto-generated by VECTOR governor -->
    </nav>
    <main class="main" id="main-content">
{sections_html}    </main>
  </div>
</body>
</html>"""

    def search_design_corpus(
        self,
        query: str,
        top_k: int = 10,
        corpora: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        BM25-style text search over the harvested UI/UX design corpus.

        Args:
            query:   Natural language query (e.g. "button hover focus state accessibility").
            top_k:   Maximum number of results to return (default 10).
            corpora: Optional list of specific CSV filenames to search.
                     Defaults to all primary corpora (ux-guidelines, design, ui-reasoning, etc.)

        Returns:
            List of result dicts sorted by relevance score (descending).
            Each dict contains: 'corpus', 'score', plus all CSV row fields.

        Example:
            results = agent.search_design_corpus("navigation mobile back button")
            # [{'corpus': 'ux-guidelines.csv', 'score': 5, 'Category': 'Navigation', ...}]
        """
        try:
            fn = _get_corpus_search()
            results = fn(query, top_k=top_k, corpora=corpora)
            logger.debug(
                f"[VECTOR][ui_designer] corpus search '{query[:40]}' "
                f"→ {len(results)} results"
            )
            return results
        except Exception as e:
            logger.warning(f"[VECTOR][ui_designer] search_design_corpus failed: {e}")
            return []

    async def answer_design_question(self, query: str) -> str:
        """LLM-backed answer for open-ended design requests (layout sketches,
        component breakdowns, UX questions) that don't map to one of this
        agent's structured task_types.

        Found via eval (KNOWN_ISSUES, TIER6 'design' category, score 0.575):
        run()'s unmatched-task_type fallback always dumped the raw
        _VECTOR_DESIGN_TOKENS dict regardless of what was actually asked —
        e.g. "I'm mocking up a simple settings screen — can you sketch out
        what components and layout it should probably have?" got back a
        flat colors/typography/spacing listing, not a layout. Judge: "no
        actual components or layout sketch." Grounded with VECTOR's own
        design tokens so the answer stays consistent with the existing
        system instead of inventing an unrelated palette.
        """
        tokens_summary = (
            f"VECTOR design system reference — colors: {list(_VECTOR_DESIGN_TOKENS['colors'].keys())}, "
            f"spacing scale: {list(_VECTOR_DESIGN_TOKENS['spacing'].keys())}, "
            f"radius: {list(_VECTOR_DESIGN_TOKENS['radius'].keys())}, "
            f"fonts: {_VECTOR_DESIGN_TOKENS['typography']['font_sans']} / "
            f"{_VECTOR_DESIGN_TOKENS['typography']['font_mono']}."
        )
        prompt = (
            "You are VECTOR's UI/UX designer. Answer the design request below "
            "directly and concretely — name the actual components, layout "
            "structure, and visual hierarchy needed. Do not just list design "
            "tokens or color codes; use them only if relevant to the answer.\n\n"
            f"{tokens_summary}\n\n"
            f"Request: {query}"
        )
        try:
            response = await asyncio.to_thread(self._llm, prompt, 25.0)
            return (response or "").strip()
        except Exception as e:
            logger.warning("[VECTOR][ui_designer] answer_design_question LLM failed: {}", e)
            return ""

    async def audit_design_consistency(self, html_content: str) -> dict:
        """LLM-assisted design audit for consistency, spacing, color usage."""
        prompt = (
            f"Audit this HTML/CSS for design consistency issues:\n{html_content[:2000]}\n\n"
            f"Check: inconsistent spacing, color not from design system, "
            f"missing focus states, hard-coded values that should be variables.\n"
            f"Return JSON: {{\"issues\": [{{\"severity\": \"high/medium/low\", \"element\": \"\", \"fix\": \"\"}}], "
            f"\"consistency_score\": 0-100}}"
        )
        try:
            response = await asyncio.to_thread(self._llm, prompt, 20.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][ui_designer] audit LLM failed: {}", e)

        return {"issues": [], "consistency_score": 75,
                "note": "Manual audit required — LLM unavailable"}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "tokens")
        try:
            if task_type == "css_variables":
                css = self.generate_css_variables()
                self.award_points(15, "css_variables_generated")
                return {"status": "ok", "css": css}

            elif task_type == "component":
                spec = self.spec_component(
                    task.get("component", "button"), task.get("props", None)
                )
                self.award_points(20, "component_specced")
                return {"status": "ok", "spec": spec}

            elif task_type == "dashboard":
                html = self.generate_dashboard_layout(task.get("sections", None))
                self.award_points(30, "dashboard_layout_generated")
                return {"status": "ok", "html": html}

            elif task_type == "audit":
                result = await self.audit_design_consistency(task.get("html", ""))
                self.award_points(20, "design_audited")
                return {"status": "ok", "audit": result}

            elif task_type == "search_corpus":
                query = task.get("query", "")
                results = self.search_design_corpus(
                    query,
                    top_k=task.get("top_k", 10),
                    corpora=task.get("corpora", None),
                )
                self.award_points(10, "corpus_searched")
                return {"status": "ok", "query": query, "results": results, "count": len(results)}

            else:  # unmatched task_type, or explicit "tokens" default
                # KNOWN_ISSUES (per-district output-quality polish pass):
                # any task_type the classifier invents that isn't one of the
                # 5 structured branches above used to land here and always
                # get the bare design-token dump — wrong for a real question
                # like "sketch a settings screen layout" (eval score 0.575).
                # If the request carries real free text (params.query /
                # top-level query|text, per commands.py's
                # {"query": body.text, "content": body.text} task shape),
                # answer it properly; only fall back to the raw token dump
                # when there's genuinely no question to answer (a literal,
                # content-free {"type": "tokens"} call, which existing
                # callers still get byte-for-byte unchanged).
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_design_question(query)
                    if answer:
                        self._get_memory().store(
                            event_type="design_question_answered",
                            content=f"UIDesigner answered: {query[:80]}",
                            tags=["design", "ui"],
                            source="ui_designer",
                        )
                        self.award_points(15, "design_question_answered")
                        return {"status": "ok", "response": answer}

                self._get_memory().store(
                    event_type="design_tokens_requested",
                    content="VECTOR design token system retrieved",
                    tags=["design", "ui"],
                    source="ui_designer",
                )
                self.award_points(10, "tokens_served")
                return {"status": "ok", "tokens": _VECTOR_DESIGN_TOKENS}

        except Exception as e:
            logger.error("[VECTOR][ui_designer] {}", e)
            self.deduct_points(30, "ui_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = UIDesigner()
        css = agent.generate_css_variables()
        print(f"[OK] css_variables: {len(css.splitlines())} CSS lines")
        spec = agent.spec_component("button", ["variant", "size", "disabled"])
        print(f"[OK] component: {spec['component']} states={len(spec['states'])}")
        html = agent.generate_dashboard_layout(["agent-grid", "metrics", "console"])
        print(f"[OK] dashboard: {len(html)} chars HTML generated")
        result = await agent.run({"type": "tokens"})
        print(f"[OK] run: status={result['status']} color_count={len(result.get('tokens', {}).get('colors', {}))}")
        print("ui_designer.py OK")

    asyncio.run(_smoke())
