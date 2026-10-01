import html as _html
import re
import sys
import uuid
import json
import asyncio as _asyncio
import concurrent.futures as _cf
from pathlib import Path
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, max_tokens: int = 1500, temperature: float = 0.5) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="report_generator",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class ReportGenerator(AgentBase):
    """
    Generates interview reports in various formats
    including markdown and PDF exports.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "ReportGenerator", "interview_prep")
        self.capabilities = ["company_specific", "export_report", "generate", "html", "interview", "json", "progress_report", "report", "session", "session_report"]
        if ghost:
            self.inherit_ghost(ghost)

        self._report_templates = {}
        self._generated_reports: list[dict] = []
        self._reports_dir = Path(__file__).parent.parent.parent.parent / "data" / "interview_reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[VECTOR][report_generator] ReportGenerator initialized")

    def generate_session_report(self, interview_id: str) -> dict:
        """
        Generate a detailed report for a completed interview session.
        """
        prompt = """Generate a comprehensive interview session report.

Create a well-structured markdown report that includes:
1. Executive Summary
2. Overall Performance Score
3. Question-by-Question Analysis
4. Strengths Demonstrated
5. Areas for Improvement
6. Specific Recommendations
7. Practice Resources
8. Next Steps

Use placeholder data where specific information isn't available.
Make the report professional and actionable.
Format with proper markdown headers and bullet points.
"""

        try:
            report_content = _llm(prompt, max_tokens=1500)

            report = {
                "id": str(uuid.uuid4()),
                "interview_id": interview_id,
                "title": f"Interview Session Report - {interview_id[:8]}",
                "content": report_content,
                "format": "markdown",
                "created_at": self._get_timestamp(),
                "metadata": {
                    "sections": self._extract_sections(report_content),
                    "word_count": len(report_content.split())
                }
            }

            self._generated_reports.append(report)
            self.award_points(15, f"session_report_generated")

            return report

        except Exception as e:
            logger.error(f"[VECTOR][report_generator] Session report failed: {e}")
            return {"interview_id": interview_id, "error": str(e)}

    def generate_progress_report(self) -> dict:
        """
        Generate an overall progress report across all interview sessions.
        """
        prompt = """Generate an interview progress report based on available tracking data.

Create a comprehensive progress report including:
1. Overall Progress Summary
2. Score Trends Over Time
3. Category-wise Performance
4. Strongest and Weakest Areas
5. Improvement Recommendations
6. Practice Plan for Next Week
7. Resources to Focus On

Use placeholder data structure where specific data isn't available.
Make recommendations specific and actionable.
"""

        try:
            report_content = _llm(prompt, max_tokens=1500)

            report = {
                "id": str(uuid.uuid4()),
                "title": "Interview Progress Report",
                "type": "progress",
                "content": report_content,
                "format": "markdown",
                "created_at": self._get_timestamp(),
                "metadata": {
                    "sections": self._extract_sections(report_content),
                    "word_count": len(report_content.split())
                }
            }

            self._generated_reports.append(report)
            self.award_points(20, "progress_report_generated")

            return report

        except Exception as e:
            logger.error(f"[VECTOR][report_generator] Progress report failed: {e}")
            return {"error": str(e)}

    def _extract_sections(self, content: str) -> list[str]:
        """Extract section headers from report content."""
        sections = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#") and line[1:].strip():
                sections.append(line.lstrip("#").strip())
        return sections

    def export_report(self, report: dict, format: str = "markdown",
                     output_path: Optional[str] = None) -> dict:
        """
        Export report to specified format.
        Formats: markdown, json, html
        """
        if format not in ("markdown", "json", "html"):
            format = "markdown"
        try:
            # CWE-22: title and output_path are caller-supplied; confine writes to the reports dir.
            base = self._reports_dir.resolve()
            if output_path is None:
                safe_title = re.sub(r'[^\w\- ]', "_", str(report.get("title", "report"))[:30]).strip() or "report"
                target = base / f"{safe_title}.{format}"
            else:
                target = Path(output_path)
                if not target.is_absolute():
                    target = base / target
                target = target.resolve()
            if not target.is_relative_to(base):
                logger.warning(f"[VECTOR][report_generator] Export refused, path outside reports dir: {output_path!r}")
                return {"status": "error", "message": "output_path must be inside the interview reports directory"}
            output_path = str(target)

            if format == "json":
                content = json.dumps(report, indent=2)
            elif format == "html":
                content = self._convert_to_html(report)
            else:
                content = self._format_markdown_report(report)

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(content, encoding="utf-8")

            self.award_points(5, f"report_exported_{format}")
            logger.info(f"[VECTOR][report_generator] Exported report to {output_path}")

            return {
                "status": "success",
                "output_path": output_path,
                "format": format
            }

        except Exception as e:
            logger.error(f"[VECTOR][report_generator] Export failed: {e}")
            return {"status": "error", "message": str(e)}

    def _format_markdown_report(self, report: dict) -> str:
        """Format report as markdown."""
        lines = [
            f"# {report.get('title', 'Interview Report')}",
            "",
            f"**Generated:** {report.get('created_at', 'N/A')}",
            "",
            "---",
            "",
        ]

        content = report.get("content", "")
        lines.append(content)

        metadata = report.get("metadata", {})
        if metadata:
            lines.extend(["", "---", "", "**Metadata:**"])
            for key, value in metadata.items():
                if key != "word_count":
                    lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def _convert_to_html(self, report: dict) -> str:
        """Convert report to HTML."""
        sections = report.get("metadata", {}).get("sections", [])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{_html.escape(str(report.get('title', 'Interview Report')))}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .meta {{ color: #7f8c8d; font-size: 0.9em; }}
        pre {{ background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{_html.escape(str(report.get('title', 'Interview Report')))}</h1>
    <p class="meta">Generated: {_html.escape(str(report.get('created_at', 'N/A')))}</p>
"""

        content = report.get("content", "")
        content_html = _html.escape(str(content)).replace("\n", "<br>\n")
        html += f"    <div class='content'>{content_html}</div>\n"

        if sections:
            html += "    <h2>Sections</h2>\n    <ul>\n"
            for section in sections:
                html += f"        <li>{_html.escape(str(section))}</li>\n"
            html += "    </ul>\n"

        html += """</body>
</html>"""

        return html

    def generate_company_specific_report(self, company: str, role: str,
                                       questions: list[dict]) -> dict:
        """
        Generate a company-specific interview preparation report.
        """
        prompt = f"""Create a comprehensive company-specific interview preparation report for:

Company: {company}
Role: {role}

Generate a report including:
1. Company Overview and Culture Fit
2. Role-Specific Preparation
3. Most Likely Interview Questions
4. Strong Answers to Prepare
5. Questions to Ask the Interviewer
6. Red Flags to Avoid
7. Day-of-Interview Checklist
8. Follow-up Strategy

Make it specific to {company} and the {role} role.
"""

        try:
            report_content = _llm(prompt, max_tokens=1500, temperature=0.5)

            report = {
                "id": str(uuid.uuid4()),
                "title": f"{company} - {role} Interview Prep",
                "type": "company_specific",
                "company": company,
                "role": role,
                "content": report_content,
                "format": "markdown",
                "created_at": self._get_timestamp()
            }

            self._generated_reports.append(report)
            self.award_points(25, f"company_report_{company}")

            return report

        except Exception as e:
            logger.error(f"[VECTOR][report_generator] Company report failed: {e}")
            return {"company": company, "role": role, "error": str(e)}

    def get_report_templates(self) -> list[str]:
        """Get available report templates."""
        return [
            "session_report",
            "progress_report",
            "company_specific",
            "weekly_summary",
            "mock_interview_feedback"
        ]

    def get_generated_reports(self, limit: int = 20) -> list[dict]:
        """Get list of generated reports."""
        return sorted(
            self._generated_reports[-limit:],
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["session_report", "progress_report", "export_report", "company_specific"]

        if task_type == "session_report":
            return self.generate_session_report(p.get("interview_id", ""))
        if task_type == "progress_report":
            return self.generate_progress_report()
        if task_type == "export_report":
            return self.export_report(p.get("report", {}), p.get("format", "markdown"), p.get("output_path"))
        if task_type == "company_specific":
            return self.generate_company_specific_report(p.get("company", ""), p.get("role", ""), p.get("questions", []))

        # 2026-08-04: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"] — "can you
        # generate my progress report?" previously hit the bare "unhandled
        # type" error stub. Route a real question to a real report instead.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            company = p.get("company", "")
            if company:
                return self.generate_company_specific_report(
                    company, p.get("role", ""), p.get("questions", [])
                )
            interview_id = p.get("interview_id", "")
            if interview_id and any(w in q for w in ("session", "last interview", "that interview")):
                return self.generate_session_report(interview_id)
            # progress_report() needs no arguments and reflects real stored
            # data — the correct default for an open-ended reporting question.
            return self.generate_progress_report()

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    generator = ReportGenerator()

    templates = generator.get_report_templates()
    print(f"Available templates: {len(templates)}")

    report = generator.generate_progress_report()
    print(f"Generated report: {report.get('title', 'N/A')}")

    print("✅ report_generator.py OK")
