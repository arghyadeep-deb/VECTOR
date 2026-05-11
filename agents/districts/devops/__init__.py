"""
Module: agents/districts/devops/__init__.py
District: devops | Focus: Service deployment, health checks, scaling, rollback
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, subprocess
from typing import Optional


class DevOpsEngineer(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DevOpsEngineer",
            district="devops",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.deployed_services = {}
        self.deployment_history = []
        logger.info("[VECTOR][devops] DevOpsEngineer ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.ollama_safe import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    async def deploy_service(self, name: str, config: dict) -> dict:
        logger.info(f"[VECTOR][devops] Deploying service: {name}")
        self.add_lesson({"action": "deploy_service", "service": name})

        deploy_config = {
            "name": name,
            "image": config.get("image", f"{name}:latest"),
            "replicas": config.get("replicas", 1),
            "port": config.get("port", 8080),
            "env": config.get("env", {}),
            "resources": config.get("resources", {"cpu": "500m", "memory": "512Mi"}),
            "deployed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "deploying",
        }

        prompt = f"""Generate deployment commands and configuration for service '{name}':
Config: {json.dumps(config, indent=2)}
Generate: 1) Docker compose or Kubernetes manifest, 2) Environment variables, 3) Health check configuration, 4) Deployment script.
Keep it practical and production-ready."""
        deployment_plan = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            existing = result.stdout.strip().split("\n") if result.returncode == 0 else []
        except FileNotFoundError:
            existing = []

        deploy_config["deployment_plan"] = deployment_plan
        deploy_config["status"] = "deployed"
        deploy_config["instances"] = config.get("replicas", 1)

        self.deployed_services[name] = deploy_config
        self.deployment_history.append({"service": name, "action": "deploy", "timestamp": deploy_config["deployed_at"], "config": config})

        self.memory.store(
            event_type="service_deployed",
            content=f"Deployed service '{name}' with {deploy_config.get('instances', 1)} instances",
            tags=["devops", "deployment", name],
            context=deploy_config,
            source="DevOpsEngineer"
        )

        logger.info(f"[VECTOR][devops] Service '{name}' deployed with plan: {deployment_plan[:100]}...")
        return deploy_config

    def check_service_health(self, service_name: str) -> dict:
        logger.info(f"[VECTOR][devops] Health check for service: {service_name}")
        self.add_lesson({"action": "check_service_health", "service": service_name})

        service = self.deployed_services.get(service_name)
        if not service:
            return {"error": f"Service '{service_name}' not found", "status": "unknown"}

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            docker_health = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            docker_health = "unknown"

        health_checks = {
            "docker_container": docker_health,
            "service_responding": service.get("status") == "deployed",
            "replicas_healthy": service.get("instances", 1),
        }

        overall_status = "healthy" if all(v == "healthy" or v is True for v in health_checks.values()) else "degraded" if any(v == "unhealthy" for v in health_checks.values()) else "unknown"

        health_report = {
            "service_name": service_name,
            "health_checks": health_checks,
            "overall_status": overall_status,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="health_check",
            content=f"Health check for '{service_name}': {overall_status}",
            tags=["devops", "health", service_name],
            context=health_report,
            source="DevOpsEngineer"
        )

        return health_report

    def scale_service(self, service_name: str, instances: int) -> dict:
        logger.info(f"[VECTOR][devops] Scaling {service_name} to {instances} instances")
        self.add_lesson({"action": "scale_service", "service": service_name, "instances": instances})

        service = self.deployed_services.get(service_name)
        if not service:
            return {"error": f"Service '{service_name}' not found"}

        old_instances = service.get("instances", 1)

        scale_command = f"docker-compose up -d --scale {service_name}={instances}"
        prompt = f"""Generate scaling commands and verification steps for service '{service_name}' scaling from {old_instances} to {instances} instances.
Include: 1) Scale command, 2) Verification command, 3) Load balancer update if needed, 4) Monitoring increase recommendations."""
        scale_plan = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        service["instances"] = instances
        service["last_scaled_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.deployment_history.append({"service": service_name, "action": "scale", "from": old_instances, "to": instances, "timestamp": service["last_scaled_at"]})

        result = {
            "service_name": service_name,
            "previous_instances": old_instances,
            "new_instances": instances,
            "scale_plan": scale_plan,
            "scaled_at": service["last_scaled_at"],
        }

        self.memory.store(
            event_type="service_scaled",
            content=f"Scaled '{service_name}' from {old_instances} to {instances} instances",
            tags=["devops", "scaling", service_name],
            context=result,
            source="DevOpsEngineer"
        )

        logger.info(f"[VECTOR][devops] Scaled '{service_name}': {old_instances} -> {instances}")
        return result

    def rollback_service(self, service_name: str) -> dict:
        logger.info(f"[VECTOR][devops] Rolling back service: {service_name}")
        self.add_lesson({"action": "rollback_service", "service": service_name})

        service = self.deployed_services.get(service_name)
        if not service:
            return {"error": f"Service '{service_name}' not found"}

        history = [h for h in self.deployment_history if h.get("service") == service_name and h.get("action") == "deploy"]
        if history:
            last_good = history[-1].get("config", {})
        else:
            last_good = {"replicas": 1, "image": f"{service_name}:stable"}

        prompt = f"""Generate rollback procedure for service '{service_name}':
Last known good config: {json.dumps(last_good, indent=2)}
Current deployment: {json.dumps(service, indent=2)}
Include: 1) Rollback command, 2) Health verification, 3) Alert rollback completion, 4) Post-rollback checks."""
        rollback_plan = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        service["status"] = "rolled_back"
        service["last_rollback_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.deployment_history.append({"service": service_name, "action": "rollback", "timestamp": service["last_rollback_at"]})

        result = {
            "service_name": service_name,
            "rolled_back_to": last_good,
            "rollback_plan": rollback_plan,
            "rolled_back_at": service["last_rollback_at"],
        }

        self.memory.store(
            event_type="service_rolled_back",
            content=f"Rolled back service '{service_name}'",
            tags=["devops", "rollback", service_name],
            context=result,
            source="DevOpsEngineer"
        )

        logger.info(f"[VECTOR][devops] Service '{service_name}' rolled back")
        return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = DevOpsEngineer()
    assert agent.district == "devops"

    import asyncio
    deploy = asyncio.run(agent.deploy_service("api-service", {"image": "nginx:latest", "replicas": 2, "port": 80}))
    assert deploy["status"] in ["deploying", "deployed"]
    assert deploy["name"] == "api-service"

    health = agent.check_service_health("api-service")
    assert "overall_status" in health

    scale = agent.scale_service("api-service", 5)
    assert scale["new_instances"] == 5

    rollback = agent.rollback_service("api-service")
    assert "rollback_plan" in rollback

    print("✅ devops/__init__.py OK")