"""Investment alert monitor — MA cross, RSI threshold, volume spike detection."""
from dataclasses import dataclass

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()


@dataclass
class Alert:
    symbol: str
    alert_type: str  # 'MA_CROSS' | 'RSI_OVERBOUGHT' | 'RSI_OVERSOLD' | 'VOLUME_SPIKE'
    severity: str    # 'LOW' | 'MED' | 'HIGH'
    message: str
    value: float | None = None

class AlertMonitor:
    """Detects trading alerts from price/volume data."""

    MA_SHORT = 20
    MA_LONG = 50
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    VOLUME_SPIKE_RATIO = 2.0  # 2x average volume

    def check_alerts(self, symbol: str, prices: list[float], volumes: list[float] = None) -> list[Alert]:
        alerts = []
        if len(prices) < self.MA_LONG:
            return alerts

        # MA Cross
        ma_short = sum(prices[-self.MA_SHORT:]) / self.MA_SHORT
        ma_long = sum(prices[-self.MA_LONG:]) / self.MA_LONG
        prev_ma_short = sum(prices[-self.MA_SHORT - 1:-1]) / self.MA_SHORT
        prev_ma_long = sum(prices[-self.MA_LONG - 1:-1]) / self.MA_LONG

        if prev_ma_short < prev_ma_long and ma_short > ma_long:
            alerts.append(Alert(symbol, "MA_CROSS", "HIGH",
                                f"Golden cross: MA{self.MA_SHORT} crossed above MA{self.MA_LONG}", ma_short))
        elif prev_ma_short > prev_ma_long and ma_short < ma_long:
            alerts.append(Alert(symbol, "MA_CROSS", "HIGH",
                                f"Death cross: MA{self.MA_SHORT} crossed below MA{self.MA_LONG}", ma_short))

        # RSI (simplified 14-period)
        if len(prices) >= 14:
            gains = [max(prices[i] - prices[i - 1], 0) for i in range(-14, 0)]
            losses = [max(prices[i - 1] - prices[i], 0) for i in range(-14, 0)]
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - 100 / (1 + rs)
                if rsi > self.RSI_OVERBOUGHT:
                    alerts.append(Alert(symbol, "RSI_OVERBOUGHT", "MED",
                                        f"RSI overbought: {rsi:.1f}", rsi))
                elif rsi < self.RSI_OVERSOLD:
                    alerts.append(Alert(symbol, "RSI_OVERSOLD", "MED",
                                        f"RSI oversold: {rsi:.1f}", rsi))

        # Volume spike
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:-1]) / 19
            if avg_vol > 0 and volumes[-1] > avg_vol * self.VOLUME_SPIKE_RATIO:
                ratio = volumes[-1] / avg_vol
                alerts.append(Alert(symbol, "VOLUME_SPIKE", "MED",
                                    f"Volume {ratio:.1f}x above average", volumes[-1]))

        return alerts

if __name__ == "__main__":
    m = AlertMonitor()
    prices = [100.0 + i * 0.5 for i in range(55)]  # Rising prices
    alerts = m.check_alerts("TEST", prices)
    print("✅ alert_monitor OK:", len(alerts), "alerts")
