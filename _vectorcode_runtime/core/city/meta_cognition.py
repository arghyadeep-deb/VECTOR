"""
V.E.C.T.O.R. MetaCognition.
Gap 8: Monthly bias detection — detects when VECTOR's reasoning patterns drift
or become biased (overconfidence, recency, domain skew, calibration error).
All data persisted to SQLite for cross-session pattern analysis.
"""
from pathlib import Path

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from loguru import logger
from core.runtime_paths import data_path

from core.config import CONFIG


class MetaCognition:
    """
    Self-reflection: monitors V.E.C.T.O.R.'s own reasoning quality,
    detects blind spots, and tracks calibration and systematic bias.
    Gap 8: monthly bias detection with SQLite persistence.
    """

    BIAS_TYPES = {
        "overconfidence": "Predicted confidence consistently exceeds actual success rate",
        "underconfidence": "Predicted confidence consistently below actual success rate",
        "recency": "Recent observations disproportionately skew confidence scores",
        "domain_skew": "Systematic over/under-confidence in a specific domain",
        "confirmation": "High-confidence thoughts cluster around the same conclusions",
    }

    _db_lock = threading.RLock()

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = data_path()
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "meta_cognition.db")
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("[VECTOR][meta_cognition] MetaCognition initialized")

    def _create_tables(self):
        with self.__class__._db_lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS thoughts (
                id TEXT PRIMARY KEY,
                thought TEXT NOT NULL,
                confidence REAL NOT NULL,
                outcome TEXT DEFAULT NULL,
                domain TEXT NOT NULL DEFAULT 'general',
                accurate INTEGER DEFAULT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blind_spots (
                id TEXT PRIMARY KEY,
                missed_signal TEXT NOT NULL,
                context TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0,
                resolution TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS calibration_errors (
                id TEXT PRIMARY KEY,
                predicted_confidence REAL NOT NULL,
                actual_success INTEGER NOT NULL,
                domain TEXT NOT NULL DEFAULT 'general',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_thoughts_created ON thoughts(created_at);
            CREATE INDEX IF NOT EXISTS idx_thoughts_domain ON thoughts(domain);
            CREATE INDEX IF NOT EXISTS idx_calibration_domain ON calibration_errors(domain);
            CREATE INDEX IF NOT EXISTS idx_calibration_created ON calibration_errors(created_at);
        """)
            self._conn.commit()

    # ── Core Observation API (original, now persisted) ───────────────────────

    def observe(
        self,
        thought: str,
        confidence: float,
        outcome: Optional[str] = None,
        domain: str = "general",
    ):
        """Record a thought and its outcome for self-analysis."""
        tid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        confidence = max(0.0, min(1.0, confidence))
        accurate = None
        if outcome is not None:
            positive_signals = {"correct", "success", "confirmed", "accurate", "right", "yes"}
            accurate = 1 if any(s in outcome.lower() for s in positive_signals) else 0
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT INTO thoughts (id, thought, confidence, outcome, domain, accurate, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (tid, thought, confidence, outcome, domain, accurate, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] observe persist failed: {e}")

    def detect_blind_spot(self, missed_signal: str, context: str) -> dict:
        """Log a missed signal (blind spot) for later analysis."""
        bid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": bid,
            "missed_signal": missed_signal,
            "context": context,
            "resolved": False,
            "created_at": now,
        }
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT INTO blind_spots (id, missed_signal, context, resolved, created_at)
                       VALUES (?, ?, ?, 0, ?)""",
                    (bid, missed_signal, context, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] detect_blind_spot persist failed: {e}")
        logger.warning(f"[VECTOR][meta_cognition] Blind spot detected: {missed_signal}")
        return entry

    def resolve_blind_spot(self, missed_signal: str, resolution: str) -> bool:
        """Mark a blind spot as resolved."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.__class__._db_lock:
                cur = self._conn.execute(
                    """UPDATE blind_spots SET resolved=1, resolution=?, resolved_at=?
                       WHERE missed_signal=? AND resolved=0""",
                    (resolution, now, missed_signal),
                )
                self._conn.commit()
            if cur.rowcount > 0:
                logger.info(f"[VECTOR][meta_cognition] Blind spot resolved: {missed_signal}")
                return True
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] resolve_blind_spot failed: {e}")
        logger.warning(f"[VECTOR][meta_cognition] Blind spot not found: {missed_signal}")
        return False

    def get_self_report(self) -> dict:
        """Generate a self-awareness report (backward-compatible)."""
        try:
            with self.__class__._db_lock:
                total = self._conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0]
                avg_conf_row = self._conn.execute(
                    "SELECT AVG(confidence) FROM thoughts"
                ).fetchone()[0]
                blind_spots = self._conn.execute(
                    "SELECT COUNT(*) FROM blind_spots"
                ).fetchone()[0]
                resolved = self._conn.execute(
                    "SELECT COUNT(*) FROM blind_spots WHERE resolved=1"
                ).fetchone()[0]
            avg_confidence = round(float(avg_conf_row), 3) if avg_conf_row else 0.0
            return {
                "total_thoughts": total,
                "avg_confidence": avg_confidence,
                "blind_spots": blind_spots,
                "blind_spots_resolved": resolved,
                "resolution_rate": round(resolved / blind_spots, 2) if blind_spots > 0 else 1.0,
            }
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] get_self_report failed: {e}")
            return {"total_thoughts": 0, "avg_confidence": 0.0, "blind_spots": 0,
                    "blind_spots_resolved": 0, "resolution_rate": 1.0}

    # ── Gap 8: Calibration Tracking ──────────────────────────────────────────

    def record_calibration_error(
        self,
        predicted_confidence: float,
        actual_success: bool,
        domain: str = "general",
    ) -> str:
        """
        Record a calibration data point: predicted confidence vs actual outcome.
        Returns the record ID.
        """
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        predicted_confidence = max(0.0, min(1.0, predicted_confidence))
        try:
            with self.__class__._db_lock:
                self._conn.execute(
                    """INSERT INTO calibration_errors
                       (id, predicted_confidence, actual_success, domain, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cid, predicted_confidence, 1 if actual_success else 0, domain, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] record_calibration_error failed: {e}")
        return cid

    def get_calibration_report(self, domain: Optional[str] = None) -> dict:
        """
        Summarise calibration quality across all recorded errors.
        Returns avg_predicted, avg_actual, calibration_error, overconfidence_rate,
        underconfidence_rate, total_samples.
        """
        try:
            if domain:
                with self.__class__._db_lock:
                    rows = self._conn.execute(
                        "SELECT predicted_confidence, actual_success FROM calibration_errors WHERE domain=?",
                        (domain,),
                    ).fetchall()
            else:
                with self.__class__._db_lock:
                    rows = self._conn.execute(
                        "SELECT predicted_confidence, actual_success FROM calibration_errors"
                    ).fetchall()
            if not rows:
                return {"total_samples": 0, "avg_predicted": 0.0, "avg_actual": 0.0,
                        "calibration_error": 0.0, "overconfidence_rate": 0.0,
                        "underconfidence_rate": 0.0}
            predicted = [float(r["predicted_confidence"]) for r in rows]
            actual = [float(r["actual_success"]) for r in rows]
            avg_predicted = sum(predicted) / len(predicted)
            avg_actual = sum(actual) / len(actual)
            calibration_error = abs(avg_predicted - avg_actual)
            overconfidence_count = sum(
                1 for p, a in zip(predicted, actual) if p - a > 0.2
            )
            underconfidence_count = sum(
                1 for p, a in zip(predicted, actual) if a - p > 0.2
            )
            n = len(rows)
            return {
                "total_samples": n,
                "avg_predicted": round(avg_predicted, 3),
                "avg_actual": round(avg_actual, 3),
                "calibration_error": round(calibration_error, 3),
                "overconfidence_rate": round(overconfidence_count / n, 3),
                "underconfidence_rate": round(underconfidence_count / n, 3),
            }
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] get_calibration_report failed: {e}")
            return {}

    # ── Gap 8: Bias Detection ────────────────────────────────────────────────

    def detect_bias(self, reasoning_samples: list[dict]) -> list[dict]:
        """
        Detect biases in a batch of reasoning samples.
        Each sample: {"thought": str, "confidence": float, "outcome": str|None, "domain": str}
        Returns list of detected bias dicts: {bias_type, severity, evidence, recommendation}.
        """
        biases = []
        if not reasoning_samples:
            return biases

        confidences = [s.get("confidence", 0.5) for s in reasoning_samples]
        outcomes = [s.get("outcome") for s in reasoning_samples]

        # Persist samples
        for s in reasoning_samples:
            self.observe(
                s.get("thought", ""),
                s.get("confidence", 0.5),
                s.get("outcome"),
                s.get("domain", "general"),
            )

        # --- Overconfidence bias ---
        # Use all samples that have any outcome (success or failure)
        with_outcomes = [
            (c, o) for c, o in zip(confidences, outcomes) if o is not None
        ]
        if len(with_outcomes) >= 3:
            avg_conf = sum(confidences) / len(confidences)
            success_words = {"correct", "success", "confirmed", "accurate", "right", "yes"}
            successes = sum(
                1 for _, o in with_outcomes
                if any(w in o.lower() for w in success_words)
            )
            success_rate = successes / len(with_outcomes)
            if avg_conf - success_rate > 0.2:
                biases.append({
                    "bias_type": "overconfidence",
                    "severity": round(min(1.0, (avg_conf - success_rate) * 2), 3),
                    "evidence": f"avg_confidence={avg_conf:.2f}, success_rate={success_rate:.2f}",
                    "recommendation": "Reduce confidence estimates by ~15-20% in similar domains",
                })

        # --- Recency bias (last 20% of samples dominate confidence) ---
        if len(confidences) >= 10:
            recent_n = max(2, len(confidences) // 5)
            recent_avg = sum(confidences[-recent_n:]) / recent_n
            earlier_avg = sum(confidences[:-recent_n]) / (len(confidences) - recent_n)
            if abs(recent_avg - earlier_avg) > 0.25:
                biases.append({
                    "bias_type": "recency",
                    "severity": round(min(1.0, abs(recent_avg - earlier_avg)), 3),
                    "evidence": f"recent_avg={recent_avg:.2f}, earlier_avg={earlier_avg:.2f}",
                    "recommendation": "Weight older observations more evenly with recent ones",
                })

        # --- Confirmation bias (high-conf thoughts cluster in one domain) ---
        # Compare domain avg against the REST (excluding that domain) to avoid dilution
        domain_counts: dict[str, list[float]] = {}
        for s in reasoning_samples:
            d = s.get("domain", "general")
            domain_counts.setdefault(d, []).append(s.get("confidence", 0.5))
        for domain, confs in domain_counts.items():
            if len(confs) >= 3 and len(confs) / len(reasoning_samples) > 0.5:
                domain_avg = sum(confs) / len(confs)
                other_confs = [
                    s.get("confidence", 0.5)
                    for s in reasoning_samples
                    if s.get("domain", "general") != domain
                ]
                if other_confs:
                    other_avg = sum(other_confs) / len(other_confs)
                    if domain_avg - other_avg > 0.25:
                        biases.append({
                            "bias_type": "confirmation",
                            "severity": round(min(1.0, domain_avg - other_avg), 3),
                            "evidence": f"domain '{domain}' avg={domain_avg:.2f} vs other domains={other_avg:.2f}",
                            "recommendation": f"Diversify reasoning beyond '{domain}' domain",
                        })

        return biases

    def detect_systematic_bias(self, window_days: int = 30) -> dict:
        """
        Detect systematic biases across stored observations over the past window_days.
        Returns {detected_biases: list, domain_analysis: dict, summary: str}.
        """
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
            with self.__class__._db_lock:
                rows = self._conn.execute(
                    """SELECT domain, confidence, accurate FROM thoughts
                       WHERE created_at >= ? AND accurate IS NOT NULL""",
                    (cutoff,),
                ).fetchall()

            if len(rows) < 5:
                return {
                    "detected_biases": [],
                    "domain_analysis": {},
                    "summary": f"Insufficient data ({len(rows)} observations with outcomes in {window_days}d window)",
                }

            domain_data: dict[str, dict] = {}
            for row in rows:
                d = row["domain"]
                if d not in domain_data:
                    domain_data[d] = {"confidences": [], "accuracies": []}
                domain_data[d]["confidences"].append(float(row["confidence"]))
                domain_data[d]["accuracies"].append(int(row["accurate"]))

            detected = []
            domain_analysis = {}
            for domain, data in domain_data.items():
                confs = data["confidences"]
                accs = data["accuracies"]
                if len(confs) < 3:
                    continue
                avg_conf = sum(confs) / len(confs)
                avg_acc = sum(accs) / len(accs)
                gap = avg_conf - avg_acc
                domain_analysis[domain] = {
                    "count": len(confs),
                    "avg_confidence": round(avg_conf, 3),
                    "avg_accuracy": round(avg_acc, 3),
                    "calibration_gap": round(gap, 3),
                }
                if gap > 0.2:
                    detected.append({
                        "bias_type": "overconfidence",
                        "domain": domain,
                        "severity": round(min(1.0, gap * 2), 3),
                        "evidence": f"avg_conf={avg_conf:.2f} vs accuracy={avg_acc:.2f}",
                    })
                elif gap < -0.2:
                    detected.append({
                        "bias_type": "underconfidence",
                        "domain": domain,
                        "severity": round(min(1.0, abs(gap) * 2), 3),
                        "evidence": f"avg_conf={avg_conf:.2f} vs accuracy={avg_acc:.2f}",
                    })

            all_confs = [float(r["confidence"]) for r in rows]
            all_accs = [int(r["accurate"]) for r in rows]
            overall_gap = (sum(all_confs) / len(all_confs)) - (sum(all_accs) / len(all_accs))
            summary = (
                f"Analyzed {len(rows)} observations over {window_days}d. "
                f"Overall calibration gap: {overall_gap:+.2f}. "
                f"{len(detected)} domain bias(es) detected."
            )
            return {
                "detected_biases": detected,
                "domain_analysis": domain_analysis,
                "summary": summary,
            }
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] detect_systematic_bias failed: {e}")
            return {"detected_biases": [], "domain_analysis": {}, "summary": "Error during analysis"}

    # ── Gap 8: Monthly Report ─────────────────────────────────────────────────

    def get_monthly_report(self) -> dict:
        """
        Comprehensive monthly bias detection and self-awareness report.
        Covers: thought summary, calibration, systematic biases, blind spots, recommendations.
        """
        try:
            self_report = self.get_self_report()
            calibration = self.get_calibration_report()
            bias_analysis = self.detect_systematic_bias(window_days=30)

            # Domain breakdown for thoughts
            with self.__class__._db_lock:
                domain_rows = self._conn.execute(
                    """SELECT domain, COUNT(*) as cnt, AVG(confidence) as avg_conf
                       FROM thoughts
                       WHERE created_at >= ?
                       GROUP BY domain""",
                    ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),),
                ).fetchall()
            domain_breakdown = {
                r["domain"]: {"count": r["cnt"], "avg_confidence": round(float(r["avg_conf"]), 3)}
                for r in domain_rows
            }

            # Blind spot resolution in last 30d
            with self.__class__._db_lock:
                bs_created = self._conn.execute(
                    "SELECT COUNT(*) FROM blind_spots WHERE created_at >= ?",
                    ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),),
                ).fetchone()[0]

            recommendations = []
            if calibration.get("overconfidence_rate", 0) > 0.3:
                recommendations.append(
                    "High overconfidence rate — apply confidence dampening (multiply by 0.8)"
                )
            if calibration.get("underconfidence_rate", 0) > 0.3:
                recommendations.append(
                    "High underconfidence rate — trust your assessments more"
                )
            if self_report["resolution_rate"] < 0.5 and self_report["blind_spots"] > 0:
                recommendations.append(
                    "Low blind-spot resolution rate — allocate time to review unresolved signals"
                )
            for bias in bias_analysis["detected_biases"]:
                recommendations.append(
                    f"Domain '{bias.get('domain', 'unknown')}': "
                    f"{self.BIAS_TYPES.get(bias['bias_type'], bias['bias_type'])}"
                )

            return {
                "period_days": 30,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "thought_summary": self_report,
                "calibration": calibration,
                "bias_analysis": bias_analysis,
                "domain_breakdown": domain_breakdown,
                "new_blind_spots_30d": bs_created,
                "recommendations": recommendations,
            }
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] get_monthly_report failed: {e}")
            return {}

    def get_all_blind_spots(self, resolved: Optional[bool] = None) -> list[dict]:
        """Return all blind spots, optionally filtered by resolved status."""
        try:
            if resolved is None:
                with self.__class__._db_lock:
                    rows = self._conn.execute("SELECT * FROM blind_spots ORDER BY created_at DESC").fetchall()
            else:
                with self.__class__._db_lock:
                    rows = self._conn.execute(
                        "SELECT * FROM blind_spots WHERE resolved=? ORDER BY created_at DESC",
                        (1 if resolved else 0,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] get_all_blind_spots failed: {e}")
            return []

    def close(self):
        try:
            with self.__class__._db_lock:
                self._conn.close()
        except Exception as e:
            logger.warning(f"[VECTOR][meta_cognition] close failed: {e}")


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name

    mc = MetaCognition(db)

    mc.observe("The user's tone suggests urgency", 0.8, "User confirmed urgent", "communications")
    mc.observe("Code review will catch the bug", 0.9, "Bug missed in review", "coding")
    mc.observe("Budget estimate is accurate", 0.85, None, "finance")

    bs = mc.detect_blind_spot("Missed KIIT exam reminder", "Calendar check was incomplete")
    assert bs["resolved"] is False

    mc.resolve_blind_spot("Missed KIIT exam reminder", "Added KIIT calendar watcher")

    report = mc.get_self_report()
    assert report["total_thoughts"] == 3
    assert report["blind_spots"] == 1
    assert report["blind_spots_resolved"] == 1

    cid = mc.record_calibration_error(0.9, False, "coding")
    assert isinstance(cid, str)
    mc.record_calibration_error(0.8, True, "coding")
    mc.record_calibration_error(0.85, False, "finance")

    cal = mc.get_calibration_report()
    assert "total_samples" in cal
    assert cal["total_samples"] == 3

    domain_cal = mc.get_calibration_report(domain="coding")
    assert domain_cal["total_samples"] == 2

    samples = [
        {"thought": f"Thought {i}", "confidence": 0.85, "outcome": "failed", "domain": "coding"}
        for i in range(6)
    ]
    biases = mc.detect_bias(samples)
    assert isinstance(biases, list)

    sys_bias = mc.detect_systematic_bias(window_days=30)
    assert "detected_biases" in sys_bias
    assert "summary" in sys_bias

    monthly = mc.get_monthly_report()
    assert "thought_summary" in monthly
    assert "calibration" in monthly
    assert "bias_analysis" in monthly
    assert "recommendations" in monthly

    all_bs = mc.get_all_blind_spots()
    assert len(all_bs) == 1

    mc.close()
    Path(db).unlink(missing_ok=True)
    print("[OK] meta_cognition.py")