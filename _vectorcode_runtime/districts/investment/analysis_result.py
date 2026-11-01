"""AnalysisResult schema — structured daily stock analysis output."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class AnalysisResult:
    symbol: str
    decision: str  # 'BUY' | 'SELL' | 'WATCH' | 'HOLD'
    score: float   # 0-100
    risk_level: str  # 'LOW' | 'MED' | 'HIGH'
    catalysts: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    price_target: float | None = None
    current_price: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "vector_analysis"

    def to_push_message(self) -> str:
        emoji = {"BUY": "📈", "SELL": "📉", "WATCH": "👁️", "HOLD": "⏸️"}.get(self.decision, "📊")
        msg = f"{emoji} {self.symbol} [{self.decision}] Score: {self.score:.0f}/100\n"
        if self.catalysts:
            msg += f"✅ Catalysts: {', '.join(self.catalysts[:2])}\n"
        if self.risk_warnings:
            msg += f"⚠️ Risks: {', '.join(self.risk_warnings[:2])}\n"
        if self.price_target:
            msg += f"🎯 Target: ₹{self.price_target:.2f}"
        return msg

if __name__ == "__main__":
    r = AnalysisResult(symbol="RELIANCE", decision="BUY", score=82.5, risk_level="MED",
                       catalysts=["Strong Q4 earnings"], risk_warnings=["High PE"])
    print("✅ analysis_result OK:", r.to_push_message())
