"""Public beta-signup endpoints for the Growth Engine.

`GET /growth/signup`  → renders the consent form (public).
`POST /growth/signup` → registers a beta tester via ``BetaSignup`` — fails closed
when signups aren't activated (activation is gated to release approval).

These are intentionally public paths (external testers); they are exempted from
auth + CSRF in middleware. The signup gate + consent + privacy + encryption in
``districts/growth/beta_signup.py`` are the real protections.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger

from core.config import CONFIG
from districts.growth.beta_signup import BetaSignup

router = APIRouter(prefix="/growth", tags=["growth"])

# Module-level singleton; inactive until BetaSignup.activate(owner_approved=True).
_signup = BetaSignup()


class SignupBody(BaseModel):
    email: str
    consent: bool = False


@router.get("/signup", response_class=HTMLResponse)
async def signup_form() -> str:
    consent_text = CONFIG["growth"].get("consent_text", "I consent.")
    brand = CONFIG["growth"].get("brand_line", "VECTOR")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{brand} — Private Beta</title></head>
<body>
  <h1>{brand}</h1>
  <h2>Join the private beta (1 month free)</h2>
  <form method="post" action="/growth/signup">
    <label>Email <input type="email" name="email" required></label>
    <label><input type="checkbox" name="consent" required> {consent_text}</label>
    <button type="submit">Sign up</button>
  </form>
</body></html>"""


@router.post("/signup")
async def signup(body: SignupBody) -> dict:
    result = _signup.register(body.email, consent=body.consent)
    if not result["ok"]:
        reason = result.get("reason", "rejected")
        code = 403 if reason == "signup_not_active" else 400
        logger.info("[VECTOR][growth][router] signup rejected: {}", reason)
        raise HTTPException(status_code=code, detail=reason)
    return result


if __name__ == "__main__":
    print("growth router OK")
