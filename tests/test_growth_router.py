"""Task 6 — public consent form (GET) + gated signup (POST)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_form_served_and_post_gated():
    from fastapi.testclient import TestClient
    from core.api.app import create_app
    c = TestClient(create_app())
    # public consent form renders
    resp = c.get("/growth/signup")
    assert resp.status_code == 200 and "consent" in resp.text.lower()
    # signups inactive by default → POST rejected (gated)
    post = c.post("/growth/signup", json={"email": "a@b.com", "consent": True})
    assert post.status_code in (403, 409)


if __name__ == "__main__":
    print("run via pytest")
