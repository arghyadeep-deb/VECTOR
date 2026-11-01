"""
Module: agents/data_analytics/__init__.py
District: data_analytics | Focus: Dataset analysis, dashboard metrics, anomaly detection, reporting
"""

import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, math, sqlite3, collections
from typing import Optional


class DataAnalytics(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DataAnalytics",
            district="data_analytics",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.analyses = {}
        logger.info("[VECTOR][data_analytics] DataAnalytics ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def analyze_dataset(self, path: str) -> dict:
        logger.info(f"[VECTOR][data_analytics] Analyzing dataset: {path}")
        self.add_lesson({"action": "analyze_dataset", "path": path})

        data_p = Path(path)
        if not data_p.exists():
            return {"error": f"Dataset not found: {path}"}

        lines = []
        try:
            if data_p.suffix == ".csv":
                content = data_p.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
            elif data_p.suffix == ".db":
                conn = sqlite3.connect(data_p, check_same_thread=False)
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor]
                sample_data = {}
                for tbl in tables[:3]:
                    cursor2 = conn.execute('SELECT * FROM "{}" LIMIT 5'.format(tbl.replace('"', '""')))
                    sample_data[tbl] = [dict(zip([d[0] for d in cursor2.description], row)) for row in cursor2]
                conn.close()
                lines = [str(sample_data)]
            else:
                lines = data_p.read_text(encoding="utf-8", errors="ignore").splitlines()[:1000]
        except Exception as e:
            # Previously this substituted a fabricated "Sample data from <name>"
            # line and went on to have the LLM "analyze" it as if it were the
            # dataset, then stored the result as a real analysis.
            logger.warning("[VECTOR][data_analytics] Could not read dataset {}: {}", data_p.name, e)
            return {"error": f"Could not read dataset '{data_p.name}': {e}"}

        sample_text = "\n".join(lines[:100])
        total_rows = len(lines)
        total_cols = len(lines[0].split(",")) if lines and "," in lines[0] else 0

        prompt = f"""Analyze this dataset:
File: {data_p.name}
Total rows: {total_rows}
Columns: {total_cols}
Sample:\n{sample_text[:1000]}
Provide: 1) Data type identification, 2) Column descriptions, 3) Data quality assessment, 4) Statistical summary, 5) Key insights from sample."""
        analysis = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        self.analyses[data_p.stem] = {
            "path": path,
            "rows": total_rows,
            "columns": total_cols,
            "analysis": analysis,
        }

        result = {
            "dataset": data_p.name,
            "rows": total_rows,
            "columns": total_cols,
            "analysis": analysis,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="dataset_analyzed",
            content=f"Analyzed dataset '{data_p.name}': {total_rows} rows, {total_cols} columns",
            tags=["data_analytics", "dataset", data_p.stem],
            context=result,
            source="DataAnalytics"
        )

        return result

    def generate_dashboard_metrics(self) -> dict:
        logger.info("[VECTOR][data_analytics] Generating dashboard metrics")
        self.add_lesson({"action": "generate_dashboard_metrics"})

        # KNOWN_ISSUES #21: EpisodicMemory() wraps a process-wide singleton
        # connection; closing a local instance closes it for every other
        # consumer too. See districts/skills/skill_mapper.py for the full note.
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        stats = mem.get_stats()

        prompt = f"""Generate dashboard metrics from these data points:
Memory stats: {json.dumps(stats, indent=2)}
Recent analyses: {list(self.analyses.keys())}
Generate: 1) Key performance indicators, 2) Trend indicators (up/down/stable), 3) Alerts if any anomalies, 4) Summary widget data for a dashboard."""
        metrics = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        result = {
            "metrics": metrics,
            "memory_stats": stats,
            "analyses_count": len(self.analyses),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="dashboard_metrics_generated",
            content=f"Generated dashboard metrics: {len(self.analyses)} analyses",
            tags=["data_analytics", "dashboard", "metrics"],
            context=result,
            source="DataAnalytics"
        )

        return result

    def detect_anomalies(self, data: list[dict]) -> dict:
        logger.info(f"[VECTOR][data_analytics] Detecting anomalies in {len(data)} records")
        self.add_lesson({"action": "detect_anomalies", "count": len(data)})

        if not data:
            return {"anomalies": [], "count": 0, "status": "no_data"}

        numeric_fields = {}
        detected_anomalies = []
        for rec_idx, record in enumerate(data):
            for key, value in record.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if not math.isfinite(value):
                    # NaN corrupts sorted()/quartiles (real outliers silently
                    # missed); inf is itself an anomaly. Report, don't compute.
                    detected_anomalies.append({"field": key, "value": str(value), "type": "non_finite", "severity": "high", "record_index": rec_idx})
                    continue
                numeric_fields.setdefault(key, []).append((rec_idx, value))

        for field, indexed in numeric_fields.items():
            values = [v for _, v in indexed]
            if len(values) < 3:
                continue
            mean_val = sum(values) / len(values)
            sorted_vals = sorted(values)
            if len(sorted_vals) >= 4:
                q1, q3 = sorted_vals[len(sorted_vals) // 4], sorted_vals[3 * len(sorted_vals) // 4]
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                for i, val in indexed:
                    if val < lower_bound or val > upper_bound:
                        detected_anomalies.append({"field": field, "value": val, "type": "statistical_outlier", "severity": "medium", "boundaries": {"lower": lower_bound, "upper": upper_bound}, "record_index": i})

        prompt = f"""Analyze these data records for contextual anomalies:
Total records: {len(data)}
Fields: {list(data[0].keys()) if data else []}
Statistical outliers found: {len(detected_anomalies)}
Outlier details: {json.dumps(detected_anomalies[:5], indent=2)}
Check for: 1) Sequential patterns that break, 2) Categorical anomalies, 3) Missing value patterns, 4) Timing anomalies.
Return JSON: {{anomalies: [{{field, value, anomaly_type, severity, description}}]}}"""
        contextual = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', contextual, re.DOTALL)
            if json_match:
                ctx_anomalies = json.loads(json_match.group(0))
            else:
                ctx_anomalies = {"anomalies": []}
        except json.JSONDecodeError:
            ctx_anomalies = {"anomalies": []}

        ctx_list = ctx_anomalies.get("anomalies", []) if isinstance(ctx_anomalies, dict) else []
        if not isinstance(ctx_list, list):
            ctx_list = []
        all_anomalies = detected_anomalies + [a for a in ctx_list if isinstance(a, dict)]

        result = {
            "total_records": len(data),
            "anomalies_detected": len(all_anomalies),
            "anomalies": all_anomalies[:20],
            "severity_breakdown": {"critical": sum(1 for a in all_anomalies if a.get("severity") == "critical"), "high": sum(1 for a in all_anomalies if a.get("severity") == "high"), "medium": sum(1 for a in all_anomalies if a.get("severity") in ["medium", "statistical_outlier"])},
            "detected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="anomalies_detected",
            content=f"Detected {len(all_anomalies)} anomalies in {len(data)} records",
            tags=["data_analytics", "anomaly_detection"],
            context=result,
            source="DataAnalytics"
        )

        return result

    def generate_report(self, analysis_type: str) -> dict:
        logger.info(f"[VECTOR][data_analytics] Generating {analysis_type} report")
        self.add_lesson({"action": "generate_report", "type": analysis_type})

        if not self.analyses:
            # No analyzed datasets: the LLM would be asked for a "comprehensive
            # report" with an empty data section and fabricate findings.
            logger.warning("[VECTOR][data_analytics] generate_report({}) called with no analyses", analysis_type)
            return {"status": "no_data", "report_type": analysis_type, "report": "", "error": "no analyses available to report on", "analyses_included": []}

        prompt = f"""Generate a comprehensive {analysis_type} analytics report.
Current analyses: {list(self.analyses.keys())}
Memory stats: {json.dumps(self.analyses)}
Include: 1) Executive summary, 2) Key findings, 3) Trend analysis, 4) Recommendations, 5) Supporting data tables, 6) Next steps."""
        report = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        result = {
            "report_type": analysis_type,
            "report": report,
            "analyses_included": list(self.analyses.keys()),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="analytics_report_generated",
            content=f"Generated {analysis_type} analytics report",
            tags=["data_analytics", "report", analysis_type],
            context=result,
            source="DataAnalytics"
        )

        return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = DataAnalytics()
    assert agent.district == "data_analytics"

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("name,age,score\nAlice,25,85\nBob,30,92\nCharlie,22,78\nDavid,35,95\n")
        csv_path = f.name

    analysis = agent.analyze_dataset(csv_path)
    assert "rows" in analysis
    assert analysis["rows"] >= 4

    metrics = agent.generate_dashboard_metrics()
    assert "metrics" in metrics

    test_data = [
        {"value": 10}, {"value": 12}, {"value": 11}, {"value": 100}, {"value": 9}
    ]
    anomalies = agent.detect_anomalies(test_data)
    assert "anomalies_detected" in anomalies

    report = agent.generate_report("monthly")
    assert "report" in report

    print("✅ data_analytics/__init__.py OK")