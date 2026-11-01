import re
import sys
import uuid
import asyncio
import datetime

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
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
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
        self.capabilities = ["finance", "money", "payment", "upi"]
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
        # Transaction amounts are sensitive financial data. Keep the amount in
        # the encrypted transaction record, not in routine HP/audit logs.
        self.award_points(5, "UPI transaction parsed")
        logger.info(
            "[VECTOR][upi_parser] parsed {} transaction [{}]",
            txn["direction"],
            txn["category"],
        )
        return txn

    def ingest_from_phone(self, count: int = 20) -> dict:
        """Pull recent SMS from the connected Android phone via ADB
        (PhoneController.get_sms_recent) and ingest any UPI/bank transaction
        messages. The last-seen SMS epoch timestamp is persisted in
        semantic_memory so re-polling never reprocesses the same messages.
        """
        from core.control.phone_controller import PhoneController
        phone = PhoneController()
        if not phone.is_connected():
            logger.debug("[VECTOR][upi_parser] no phone connected — skipping SMS poll")
            return {"status": "no_phone", "ingested": 0}

        last_fact = self._memory.recall_fact("upi_parser:last_sms_ts")
        last_value = last_fact.get("value") if last_fact else None
        last_ts = int(last_value) if last_value and str(last_value).isdigit() else 0

        messages = phone.get_sms_recent(count)
        ingested = 0
        newest_ts = last_ts
        for msg in messages:
            try:
                ts = int(msg.get("timestamp", "0"))
            except (TypeError, ValueError):
                ts = 0
            if ts <= last_ts:
                continue
            newest_ts = max(newest_ts, ts)
            if self.ingest(msg.get("body", "")) is not None:
                ingested += 1

        if newest_ts > last_ts:
            self._memory.remember(
                key="upi_parser:last_sms_ts", value=str(newest_ts),
                category="upi_parser_state", confidence=1.0,
            )

        if ingested:
            logger.info(f"[VECTOR][upi_parser] ingested {ingested} transaction SMS via ADB")
        return {"status": "ok", "scanned": len(messages), "ingested": ingested}

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

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if task.get("type") == "poll_sms":
            return self.ingest_from_phone(p.get("count", 20))
        sms = p.get("sms", "")
        if sms:
            result = parse_sms(sms)
            if result:
                self.ingest(sms)
                return {"status": "ok", "transaction": result}
            return {"status": "not_financial"}
        txns = self.fetch_transactions(p.get("days", 30))
        return {"status": "ok", "transactions": txns, "count": len(txns)}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][upi_parser] run_forever — polling phone SMS via ADB every 5min")
        while self.is_alive:
            try:
                self.ingest_from_phone()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"[VECTOR][upi_parser] tick: {e}")
                await asyncio.sleep(60)
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
