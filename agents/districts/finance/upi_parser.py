import re
import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from loguru import logger

# UPI SMS patterns (Indian banks)
_UPI_PATTERNS = [
    # HDFC, SBI, ICICI, Axis, Paytm, PhonePe, GPay
    re.compile(
        r"(?:Rs\.?|INR)\s*([\d,]+\.?\d*)\s+(?:debited|credited|paid|received|sent)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:debited|credited|paid|received|sent)\s+(?:Rs\.?|INR)\s*([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"UPI[:/\s]+(?:Ref|Txn|ID)[\s:]*(\w+)",
        re.IGNORECASE,
    ),
]

_MERCHANT_PATTERN = re.compile(
    r"(?:to|from|at|by)\s+([A-Za-z0-9\s&]+?)(?:\s+on|\s+Ref|\s+UPI|\s+A/C|\.|$)",
    re.IGNORECASE,
)

_CATEGORIES = {
    "food": ["swiggy", "zomato", "restaurant", "cafe", "food"],
    "transport": ["ola", "uber", "rapido", "metro", "bus", "fuel", "petrol"],
    "education": ["kiit", "college", "course", "udemy", "book"],
    "utilities": ["electricity", "recharge", "airtel", "jio", "broadband"],
    "shopping": ["amazon", "flipkart", "myntra", "meesho"],
    "health": ["pharmacy", "doctor", "hospital", "medicine"],
    "entertainment": ["netflix", "spotify", "prime", "hotstar"],
}


def _categorise(merchant: str, description: str) -> str:
    text = (merchant + " " + description).lower()
    for cat, keywords in _CATEGORIES.items():
        if any(k in text for k in keywords):
            return cat
    return "other"


def parse_sms(sms_text: str) -> dict | None:
    """
    Parse a UPI/bank SMS and return structured transaction dict.
    Returns None if not a financial SMS.
    """
    amount = None
    for pat in _UPI_PATTERNS[:2]:
        m = pat.search(sms_text)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
            break

    if amount is None:
        return None

    direction = "debit"
    lower = sms_text.lower()
    if any(w in lower for w in ["credited", "received", "added"]):
        direction = "credit"

    merchant = ""
    m = _MERCHANT_PATTERN.search(sms_text)
    if m:
        merchant = m.group(1).strip()

    category = _categorise(merchant, sms_text)

    return {
        "amount": amount,
        "direction": direction,
        "merchant": merchant,
        "category": category,
        "raw": sms_text[:200],
        "timestamp": datetime.datetime.now().isoformat(),
    }


class UPIParser(AgentBase):
    """
    Parses UPI/bank SMS texts (fed via ADB or manual input) into structured
    expense records stored in episodic_memory.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="UPIParser",
            district="finance",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        logger.info(f"[VECTOR][upi_parser] ready gen={generation}")

    def ingest(self, sms_text: str) -> dict | None:
        """Parse one SMS and store if financial."""
        txn = parse_sms(sms_text)
        if txn is None:
            return None

        self._memory.store(
            event_type="upi_transaction",
            content=(
                f"{txn['direction'].upper()} Rs.{txn['amount']:.2f} "
                f"{'to' if txn['direction']=='debit' else 'from'} {txn['merchant']} [{txn['category']}]"
            ),
            tags=["finance", "upi", txn["direction"], txn["category"]],
            source="upi_parser",
        )
        self._memory.remember(
            key=f"txn:{txn['timestamp']}",
            value=str(txn),
            category="finance_transaction",
            confidence=0.9,
        )
        self.award_points(5, f"UPI parsed: Rs.{txn['amount']}")
        logger.info(f"[VECTOR][upi_parser] {txn['direction']} Rs.{txn['amount']} [{txn['category']}]")
        return txn

    def fetch_transactions(self, days: int = 30) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content, tags, timestamp FROM episodic_memory "
                "WHERE event_type = 'upi_transaction' AND timestamp > ? ORDER BY timestamp DESC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][upi_parser] fetch failed: {e}")
            return []

    async def run_forever(self) -> None:
        logger.info("[VECTOR][upi_parser] run_forever — waiting for SMS ingestion calls")
        while self.is_alive:
            try:
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"[VECTOR][upi_parser] tick: {e}")
        logger.warning("[VECTOR][upi_parser] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = UPIParser()
    assert bot.health_points == 500

    test_sms = "Rs.250 debited from A/C XX1234 to Zomato on 07-05-2026. UPI Ref: 123456789"
    txn = bot.ingest(test_sms)
    assert txn is not None
    assert txn["amount"] == 250.0
    assert txn["direction"] == "debit"
    assert txn["category"] == "food"

    none_txn = bot.ingest("Your OTP is 123456. Do not share.")
    assert none_txn is None

    print(f"OK upi_parser.py HP={bot.health_points} txn={txn['amount']} cat={txn['category']}")
