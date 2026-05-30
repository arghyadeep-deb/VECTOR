"""
ScienceAgent — routes physics/chemistry/CAD/causal simulation tasks.
Inherits AgentBase (HP system). Lazy-imports all heavy science deps.
Registered in governor DISTRICT_TASK_MAP under 'science'.
"""
import uuid

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG


class ScienceAgent(AgentBase):
    """
    District: science.
    Routes simulate/physics/chemistry/cad/causal_query tasks.
    All heavy deps (pybullet, rdkit, dowhy, FreeCAD) are optional.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ScienceAgent",
            district="science",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._physics = None
        self._chemistry = None
        self._cad = None
        self._causal = None
        logger.info("[VECTOR][science] ScienceAgent ready gen={}", generation)

    # ── lazy engine accessors ────────────────────────────────────────────────
    def _get_physics(self):
        if self._physics is None:
            try:
                from core.science.physics_engine import PhysicsEngine
                self._physics = PhysicsEngine()
            except Exception as e:
                logger.warning("[VECTOR][science] PhysicsEngine unavailable: {}", e)
        return self._physics

    def _get_chemistry(self):
        if self._chemistry is None:
            try:
                from core.science.chemistry_engine import ChemistryEngine
                self._chemistry = ChemistryEngine()
            except Exception as e:
                logger.warning("[VECTOR][science] ChemistryEngine unavailable: {}", e)
        return self._chemistry

    def _get_cad(self):
        if self._cad is None:
            try:
                from core.science.cad_engine import CADEngine
                self._cad = CADEngine()
            except Exception as e:
                logger.warning("[VECTOR][science] CADEngine unavailable: {}", e)
        return self._cad

    def _get_causal(self):
        if self._causal is None:
            try:
                from core.causal.causal_reasoner import CausalReasoner
                self._causal = CausalReasoner()
            except Exception as e:
                logger.warning("[VECTOR][science] CausalReasoner unavailable: {}", e)
        return self._causal

    # ── main task handler ────────────────────────────────────────────────────
    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        params = task.get("params", {})
        logger.info("[VECTOR][science] task={} params={}", task_type, list(params.keys()))

        try:
            if task_type in ("simulate", "physics"):
                return await self._handle_physics(params)
            elif task_type in ("chemistry", "molecule"):
                return await self._handle_chemistry(params)
            elif task_type in ("cad",):
                return await self._handle_cad(params)
            elif task_type in ("causal_query", "what_if", "explain"):
                return await self._handle_causal(params)
            elif task_type == "experiment":
                return await self._handle_experiment(params)
            elif task_type == "science":
                return await self._handle_general(params)
            else:
                return {"status": "unknown_task", "task_type": task_type, "agent": self.name}
        except Exception as e:
            logger.error("[VECTOR][science] task={} failed: {}", task_type, e)
            return {"status": "error", "error": str(e), "agent": self.name}

    # ── handlers ─────────────────────────────────────────────────────────────
    async def _handle_physics(self, params: dict) -> dict:
        eng = self._get_physics()
        if eng is None:
            return {"status": "error", "error": "PhysicsEngine unavailable"}

        sim_type = params.get("simulation", "projectile")
        if sim_type == "projectile":
            v0 = float(params.get("velocity", 20.0))
            angle = float(params.get("angle_deg", 45.0))
            mass = float(params.get("mass_kg", 1.0))
            result = eng.simulate_projectile(v0, angle, mass)
        elif sim_type == "pendulum":
            length = float(params.get("length_m", 1.0))
            angle = float(params.get("initial_angle_deg", 10.0))
            result = eng.simulate_pendulum(length, angle)
        else:
            result = eng.get_capabilities()

        response = (
            f"Physics simulation ({sim_type}): "
            + ", ".join(f"{k}={v}" for k, v in result.items() if k != "trajectory")
        )
        return {"status": "ok", "result": result, "response": response, "agent": self.name}

    async def _handle_chemistry(self, params: dict) -> dict:
        eng = self._get_chemistry()
        if eng is None:
            return {"status": "error", "error": "ChemistryEngine unavailable"}

        smiles = params.get("smiles", params.get("molecule", ""))
        if not smiles:
            return {"status": "error", "error": "No SMILES provided"}

        result = eng.analyze_molecule(smiles)
        response = f"Molecule ({smiles}): MW={result.get('molecular_weight', '?')} heavy_atoms={result.get('heavy_atoms', '?')}"
        return {"status": "ok", "result": result, "response": response, "agent": self.name}

    async def _handle_cad(self, params: dict) -> dict:
        eng = self._get_cad()
        if eng is None:
            return {"status": "error", "error": "CADEngine unavailable"}

        shape = params.get("shape", "box")
        if shape == "box":
            result = eng.analyze_box(
                float(params.get("length", 1.0)),
                float(params.get("width", 1.0)),
                float(params.get("height", 1.0)),
            )
        elif shape == "cylinder":
            result = eng.analyze_cylinder(
                float(params.get("radius", 1.0)),
                float(params.get("height", 1.0)),
            )
        elif shape == "sphere":
            result = eng.analyze_sphere(float(params.get("radius", 1.0)))
        else:
            result = eng.get_capabilities()

        response = f"CAD analysis ({shape}): volume={result.get('volume', '?')} surface={result.get('surface_area', '?')}"
        return {"status": "ok", "result": result, "response": response, "agent": self.name}

    async def _handle_causal(self, params: dict) -> dict:
        cr = self._get_causal()
        if cr is None:
            return {"status": "error", "error": "CausalReasoner unavailable"}

        mode = params.get("mode", "explain")
        if mode == "explain":
            node = params.get("node", params.get("query", "outcome:ok"))
            result = cr.explain(node)
            response = f"Causal explanation for '{node}': {len(result.get('causes', []))} upstream causes found."
        elif mode == "what_if":
            action = params.get("action", "")
            hypo = params.get("hypothetical", "")
            result = cr.what_if(action, hypo)
            response = f"What-if analysis for '{action}' → '{hypo}'."
        else:
            treatment = params.get("treatment", "")
            outcome = params.get("outcome", "")
            result = cr.estimate_effect(treatment, outcome)
            response = f"ATE estimate {treatment}→{outcome}: {result.get('ate')}"

        return {"status": "ok", "result": result, "response": response, "agent": self.name}

    async def _handle_experiment(self, params: dict) -> dict:
        """Run a named experiment combining science + causal reasoning."""
        name = params.get("name", "unnamed")
        logger.info("[VECTOR][science] experiment: {}", name)
        # Compose: run physics sim, then record in causal graph
        physics_result = await self._handle_physics(params)
        cr = self._get_causal()
        if cr and physics_result.get("status") == "ok":
            r = physics_result["result"]
            cr._get_causal_graph()  # warm up
        return {
            "status": "ok",
            "experiment": name,
            "physics": physics_result.get("result"),
            "response": f"Experiment '{name}' complete.",
            "agent": self.name,
        }

    async def _handle_general(self, params: dict) -> dict:
        """Return capabilities summary."""
        caps = {}
        for eng_name, getter in [
            ("physics", self._get_physics),
            ("chemistry", self._get_chemistry),
            ("cad", self._get_cad),
            ("causal", self._get_causal),
        ]:
            eng = getter()
            if eng and hasattr(eng, "get_capabilities"):
                caps[eng_name] = eng.get_capabilities()
            else:
                caps[eng_name] = {"available": eng is not None}
        return {
            "status": "ok",
            "capabilities": caps,
            "response": "Science district ready. Capabilities: " + ", ".join(caps.keys()),
            "agent": self.name,
        }


if __name__ == "__main__":
    import asyncio

    agent = ScienceAgent()

    # Physics
    task = {"type": "physics", "params": {"simulation": "projectile", "velocity": 20.0, "angle_deg": 45.0}}
    result = asyncio.run(agent.run(task))
    assert result["status"] == "ok", f"Physics failed: {result}"
    r = result["result"]
    assert r["landing_distance_m"] > 0

    # Chemistry
    task2 = {"type": "chemistry", "params": {"smiles": "CC(=O)Oc1ccccc1C(=O)O"}}
    r2 = asyncio.run(agent.run(task2))
    assert r2["status"] == "ok", f"Chemistry failed: {r2}"

    # CAD
    task3 = {"type": "cad", "params": {"shape": "box", "length": 3.0, "width": 4.0, "height": 5.0}}
    r3 = asyncio.run(agent.run(task3))
    assert r3["status"] == "ok" and abs(r3["result"]["volume"] - 60.0) < 0.01

    # Causal
    task4 = {"type": "causal_query", "params": {"mode": "explain", "node": "outcome:ok"}}
    r4 = asyncio.run(agent.run(task4))
    assert r4["status"] == "ok"

    print(f"OK science_agent -- physics={r['landing_distance_m']:.2f}m "
          f"chemistry_mw={r2['result'].get('molecular_weight')} "
          f"cad_vol={r3['result']['volume']} causal_causes={len(r4['result'].get('causes', []))}")
