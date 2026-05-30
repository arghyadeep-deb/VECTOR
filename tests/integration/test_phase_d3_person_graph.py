"""D3 tests — Person knowledge graph: /brain/persons endpoints + PersonGraph.tsx."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path


_TEST_PID = "d3_test_alice_001"
_TEST_PID2 = "d3_test_bob_002"


def _ensure_test_persons():
    """Ensure test persons exist before tests that read them."""
    from core.brain.person_model import PersonModel
    pm = PersonModel()
    if not pm.person_exists(_TEST_PID):
        pm.add_person(
            person_id=_TEST_PID,
            name="Alice D3",
            relationship_type="colleague",
        )
        pm.update_trust(_TEST_PID, 0.35)  # set trust to 0.85
    if not pm.person_exists(_TEST_PID2):
        pm.add_person(
            person_id=_TEST_PID2,
            name="Bob D3",
            relationship_type="acquaintance",
        )


# ── PersonModel existing API ──────────────────────────────────────────────────


class TestPersonModelAPI(unittest.TestCase):
    """PersonModel has required D3 methods."""

    def setUp(self):
        _ensure_test_persons()

    def test_get_all_persons_returns_list(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        result = pm.get_all_persons()
        self.assertIsInstance(result, list)

    def test_get_all_persons_has_test_alice(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        # get_all_persons uses 'id' field (not 'person_id')
        ids = [p.get("id") or p.get("person_id") for p in pm.get_all_persons()]
        self.assertIn(_TEST_PID, ids)

    def test_get_model_returns_dict(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        model = pm.get_model(_TEST_PID)
        self.assertIsNotNone(model)
        self.assertIsInstance(model, dict)

    def test_get_model_has_trust(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        model = pm.get_model(_TEST_PID)
        # PersonModel stores trust as trust_score
        self.assertTrue("trust_score" in model or "trust" in model)

    def test_update_belief_succeeds(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        ok = pm.update_belief(_TEST_PID, "preferred_language", "Python", 0.9)
        self.assertTrue(ok)

    def test_update_trust_returns_float(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        new_trust = pm.update_trust(_TEST_PID, 0.01)
        self.assertIsInstance(new_trust, float)

    def test_update_trust_clamps_to_zero_one(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        trust = pm.update_trust(_TEST_PID, 100.0)
        self.assertLessEqual(trust, 1.0)

    def test_get_interaction_history_returns_list(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        hist = pm.get_interaction_history(_TEST_PID, limit=10)
        self.assertIsInstance(hist, list)

    def test_person_exists_true(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        self.assertTrue(pm.person_exists(_TEST_PID))

    def test_person_exists_false_for_unknown(self):
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        self.assertFalse(pm.person_exists("completely_unknown_xyz_d3"))


# ── GET /brain/persons ────────────────────────────────────────────────────────


class TestGetPersonsEndpoint(unittest.TestCase):
    """GET /brain/persons returns persons list."""

    def setUp(self):
        _ensure_test_persons()

    def test_get_persons_returns_persons_key(self):
        result = asyncio.run(self._call())
        self.assertIn("persons", result)

    def test_get_persons_returns_count_key(self):
        result = asyncio.run(self._call())
        self.assertIn("count", result)

    def test_get_persons_count_matches_list(self):
        result = asyncio.run(self._call())
        self.assertEqual(result["count"], len(result["persons"]))

    def test_get_persons_includes_alice(self):
        result = asyncio.run(self._call())
        # get_all_persons returns dicts with 'id' or 'person_id' depending on PersonModel version
        ids = [p.get("id") or p.get("person_id") for p in result["persons"]]
        self.assertIn(_TEST_PID, ids)

    @staticmethod
    async def _call() -> dict:
        from core.api.routers.brain import get_persons
        return await get_persons()


# ── GET /brain/persons/{id} ───────────────────────────────────────────────────


class TestGetPersonEndpoint(unittest.TestCase):
    """GET /brain/persons/{id} returns full model + interaction history."""

    def setUp(self):
        _ensure_test_persons()

    def test_returns_person_key(self):
        result = asyncio.run(self._call(_TEST_PID))
        self.assertIn("person", result)

    def test_returns_interaction_history_key(self):
        result = asyncio.run(self._call(_TEST_PID))
        self.assertIn("interaction_history", result)

    def test_interaction_history_is_list(self):
        result = asyncio.run(self._call(_TEST_PID))
        self.assertIsInstance(result["interaction_history"], list)

    def test_person_has_trust(self):
        result = asyncio.run(self._call(_TEST_PID))
        person = result["person"]
        self.assertTrue("trust_score" in person or "trust" in person)

    def test_unknown_person_raises_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._call("unknown_d3_zzz"))
        self.assertEqual(ctx.exception.status_code, 404)

    @staticmethod
    async def _call(pid: str) -> dict:
        from core.api.routers.brain import get_person
        return await get_person(pid)


# ── PUT /brain/persons/{id}/belief ────────────────────────────────────────────


class TestUpdateBeliefEndpoint(unittest.TestCase):
    """PUT /brain/persons/{id}/belief updates beliefs and reflects on next read."""

    def setUp(self):
        _ensure_test_persons()

    def test_update_belief_returns_updated_true(self):
        from core.api.routers.brain import UpdateBeliefReq
        req = UpdateBeliefReq(key="test_belief_d3", value="yes", confidence=0.9)
        result = asyncio.run(self._call(_TEST_PID, req))
        self.assertTrue(result["updated"])

    def test_update_belief_unknown_person_raises_404(self):
        from fastapi import HTTPException
        from core.api.routers.brain import UpdateBeliefReq
        req = UpdateBeliefReq(key="key", value="val")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._call("unknown_xyz_d3", req))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_belief_persists_after_update(self):
        from core.api.routers.brain import UpdateBeliefReq, get_person
        req = UpdateBeliefReq(key="d3_persistent_key", value="d3_value", confidence=0.8)
        asyncio.run(self._call(_TEST_PID, req))
        detail = asyncio.run(get_person(_TEST_PID))
        beliefs = detail["person"].get("beliefs", {})
        # beliefs dict: {topic: {"belief": ..., "confidence": ...}} or {topic: belief_str}
        entry = beliefs.get("d3_persistent_key")
        if isinstance(entry, dict):
            self.assertEqual(entry.get("belief"), "d3_value")
        else:
            self.assertEqual(entry, "d3_value")

    @staticmethod
    async def _call(pid: str, req) -> dict:
        from core.api.routers.brain import update_person_belief
        return await update_person_belief(pid, req)


# ── PUT /brain/persons/{id}/trust ─────────────────────────────────────────────


class TestUpdateTrustEndpoint(unittest.TestCase):
    """PUT /brain/persons/{id}/trust adjusts trust and reflects on next read."""

    def setUp(self):
        _ensure_test_persons()

    def test_update_trust_returns_new_trust(self):
        from core.api.routers.brain import UpdateTrustReq
        req = UpdateTrustReq(delta=0.01)
        result = asyncio.run(self._call(_TEST_PID, req))
        self.assertIn("new_trust", result)

    def test_new_trust_is_float(self):
        from core.api.routers.brain import UpdateTrustReq
        req = UpdateTrustReq(delta=-0.01)
        result = asyncio.run(self._call(_TEST_PID, req))
        self.assertIsInstance(result["new_trust"], float)

    def test_unknown_person_raises_404(self):
        from fastapi import HTTPException
        from core.api.routers.brain import UpdateTrustReq
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._call("unknown_d3_zzz", UpdateTrustReq(delta=0.1)))
        self.assertEqual(ctx.exception.status_code, 404)

    @staticmethod
    async def _call(pid: str, req) -> dict:
        from core.api.routers.brain import update_person_trust
        return await update_person_trust(pid, req)


# ── PersonGraph.tsx component ─────────────────────────────────────────────────


class TestPersonGraphDashboard(unittest.TestCase):
    """dashboard/src/components/panels/PersonGraph.tsx exists with required features."""

    def _read(self, rel: str) -> str:
        return (Path(__file__).parent.parent.parent / rel).read_text(encoding="utf-8")

    def test_person_graph_tsx_exists(self):
        path = Path(__file__).parent.parent.parent / "dashboard/src/components/panels/PersonGraph.tsx"
        self.assertTrue(path.exists())

    def test_exports_person_graph(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("export function PersonGraph", src)

    def test_fetches_persons_endpoint(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("/brain/persons", src)

    def test_has_svg_graph(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("<svg", src)

    def test_has_click_handler(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("onClick", src)

    def test_has_trust_editing(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("/trust", src)

    def test_has_belief_editing(self):
        src = self._read("dashboard/src/components/panels/PersonGraph.tsx")
        self.assertIn("/belief", src)

    def test_app_tsx_imports_person_graph(self):
        src = self._read("dashboard/src/App.tsx")
        self.assertIn("PersonGraph", src)

    def test_app_tsx_has_persons_panel(self):
        src = self._read("dashboard/src/App.tsx")
        self.assertIn("'persons'", src)

    def test_brain_all_includes_person_endpoints(self):
        import core.api.routers.brain as mod
        self.assertIn("get_persons", mod.__all__)
        self.assertIn("get_person", mod.__all__)
        self.assertIn("update_person_belief", mod.__all__)
        self.assertIn("update_person_trust", mod.__all__)


if __name__ == "__main__":
    unittest.main()
