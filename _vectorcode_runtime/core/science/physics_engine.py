"""
PhysicsEngine — PyBullet simulation wrapper.
Lazy-imports pybullet; degrades cleanly to analytical fallback if not installed.
Architecture invariant: loop must never crash on ImportError.
"""

import math
from typing import Any
from loguru import logger
from core.config import CONFIG


_GRAVITY = CONFIG.get("science", {}).get("gravity", -9.81)


class PhysicsEngine:
    """
    Runs physics simulations via PyBullet.
    Degrades to analytical approximations if pybullet is not installed.
    """

    def __init__(self):
        self._pybullet = None
        self._physics_client = None
        self._available: bool | None = None
        logger.info("[VECTOR][physics] PhysicsEngine ready")

    def _check_pybullet(self) -> bool:
        if self._available is None:
            try:
                import pybullet as pb
                self._pybullet = pb
                self._available = True
                logger.debug("[VECTOR][physics] PyBullet available")
            except ImportError:
                self._available = False
                logger.debug("[VECTOR][physics] PyBullet not installed — analytical mode")
        return self._available

    def _connect(self) -> bool:
        if not self._check_pybullet():
            return False
        if self._physics_client is not None:
            return True
        try:
            self._physics_client = self._pybullet.connect(self._pybullet.DIRECT)
            self._pybullet.setGravity(0, 0, _GRAVITY, physicsClientId=self._physics_client)
            return True
        except Exception as e:
            logger.warning("[VECTOR][physics] PyBullet connect failed: {}", e)
            self._physics_client = None
            return False

    def _disconnect(self) -> None:
        if self._physics_client is not None and self._pybullet:
            try:
                self._pybullet.disconnect(self._physics_client)
            except Exception as e:
                logger.warning("[VECTOR][physics] disconnect failed: {}", e)
            self._physics_client = None

    # ── public simulations ────────────────────────────────────────────────────
    def simulate_projectile(
        self,
        initial_velocity: float,
        angle_deg: float,
        mass_kg: float = 1.0,
        steps: int = 100,
        dt: float = 0.05,
    ) -> dict:
        """
        Simulate projectile motion. Returns landing distance, max height, time.
        Uses PyBullet if available, else analytical 2D kinematics.
        """
        if self._connect():
            return self._pybullet_projectile(initial_velocity, angle_deg, mass_kg, steps, dt)
        return self._analytical_projectile(initial_velocity, angle_deg)

    def simulate_pendulum(
        self,
        length_m: float = 1.0,
        initial_angle_deg: float = 10.0,
        steps: int = 200,
        dt: float = 0.02,
    ) -> dict:
        """Pendulum simulation. Returns period, max_velocity, trajectory list."""
        g = abs(_GRAVITY)
        # Small-angle approximation for period (always analytical — reliable)
        period = 2 * math.pi * math.sqrt(length_m / g)
        omega = math.sqrt(g / length_m)
        theta0 = math.radians(initial_angle_deg)
        trajectory = []
        for i in range(steps):
            t = i * dt
            theta = theta0 * math.cos(omega * t)
            v = -theta0 * omega * math.sin(omega * t) * length_m
            trajectory.append({"t": round(t, 3), "theta_deg": round(math.degrees(theta), 3), "v": round(v, 4)})
        return {
            "period_s": round(period, 4),
            "max_velocity_ms": round(abs(theta0 * omega * length_m), 4),
            "trajectory": trajectory[:20],
            "method": "analytical",
        }

    def get_capabilities(self) -> dict:
        return {
            "pybullet_available": self._check_pybullet(),
            "simulations": ["projectile", "pendulum"],
            "mode": "pybullet" if self._check_pybullet() else "analytical",
        }

    # ── PyBullet implementation ───────────────────────────────────────────────
    def _pybullet_projectile(self, v0: float, angle_deg: float, mass: float, steps: int, dt: float) -> dict:
        pb = self._pybullet
        client = self._physics_client
        try:
            angle_rad = math.radians(angle_deg)
            vx = v0 * math.cos(angle_rad)
            vz = v0 * math.sin(angle_rad)
            col = pb.createCollisionShape(pb.GEOM_SPHERE, radius=0.1, physicsClientId=client)
            body = pb.createMultiBody(
                baseMass=mass,
                baseCollisionShapeIndex=col,
                basePosition=[0, 0, 0.1],
                physicsClientId=client,
            )
            pb.resetBaseVelocity(body, linearVelocity=[vx, 0, vz], physicsClientId=client)
            max_height = 0.0
            for _ in range(steps):
                pb.stepSimulation(physicsClientId=client)
                pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=client)
                max_height = max(max_height, pos[2])
                if pos[2] < 0:
                    break
            landing_x = pos[0]
            pb.removeBody(body, physicsClientId=client)
            return {
                "landing_distance_m": round(landing_x, 4),
                "max_height_m": round(max_height, 4),
                "method": "pybullet",
            }
        except Exception as e:
            logger.warning("[VECTOR][physics] pybullet projectile failed: {}, using analytical", e)
            return self._analytical_projectile(v0, angle_deg)

    def _analytical_projectile(self, v0: float, angle_deg: float) -> dict:
        g = abs(_GRAVITY)
        angle_rad = math.radians(angle_deg)
        vx = v0 * math.cos(angle_rad)
        vz = v0 * math.sin(angle_rad)
        t_flight = 2 * vz / g
        distance = vx * t_flight
        max_height = (vz ** 2) / (2 * g)
        return {
            "landing_distance_m": round(distance, 4),
            "max_height_m": round(max_height, 4),
            "time_of_flight_s": round(t_flight, 4),
            "method": "analytical_kinematics",
        }

    def __del__(self):
        self._disconnect()


if __name__ == "__main__":
    eng = PhysicsEngine()
    caps = eng.get_capabilities()
    print(f"  mode={caps['mode']} pybullet={caps['pybullet_available']}")

    proj = eng.simulate_projectile(20.0, 45.0)
    assert "landing_distance_m" in proj, f"Missing landing_distance_m: {proj}"
    assert proj["landing_distance_m"] > 0, "Landing distance must be positive"

    pend = eng.simulate_pendulum(1.0, 10.0)
    assert "period_s" in pend
    assert abs(pend["period_s"] - 2.006) < 0.1, f"Period off: {pend['period_s']}"

    print(f"OK physics_engine -- projectile={proj['landing_distance_m']:.2f}m "
          f"pendulum_period={pend['period_s']}s method={proj['method']}")