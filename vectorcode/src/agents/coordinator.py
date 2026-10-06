"""VectorCode v3 SwarmCoordinator — multi-agent coordination with topologies."""

from typing import Any, Optional

from loguru import logger

from agents.agent import Agent

class SwarmCoordinator:
    def __init__(self, topology: str = "mesh", **kwargs):
        self.topology = topology
        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, Any] = {}
        self._initialized = False

    async def initialize(self):
        if self._initialized: return
        self._initialized = True
        logger.info(f"SwarmCoordinator initialized ({self.topology} topology)")

    async def shutdown(self):
        for a in self._agents.values():
            a.terminate()
        self._agents.clear()
        self._tasks.clear()
        self._initialized = False

    def spawn_agent(self, agent_type: str, **kwargs) -> Agent:
        import uuid
        agent_id = kwargs.pop("agent_id", f"agent-{uuid.uuid4().hex[:8]}")
        agent = Agent(agent_id, agent_type, **kwargs)
        self._agents[agent_id] = agent
        logger.info(f"Spawned {agent_type} agent: {agent_id}")
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def list_agents(self, status: Optional[str] = None) -> list[Agent]:
        if status:
            return [a for a in self._agents.values() if a.status == status]
        return list(self._agents.values())

    async def assign_task(self, task: dict) -> Optional[str]:
        task_type = task.get("type", "general")
        task_id = task.get("id", f"task-{id(task)}")
        if task_id in self._tasks:
            raise ValueError(f"task id already exists: {task_id}")

        candidates = [a for a in self._agents.values()
                      if a.can_execute(task_type) and task_type in a.capabilities]
        if not candidates:
            candidates = [a for a in self._agents.values() if a.can_execute(task_type)]

        if not candidates:
            logger.warning(f"No available agent for task {task_id}")
            return None

        agent = candidates[0]
        agent.assign_task(task)
        self._tasks[task_id] = {"agent": agent.id, "task": task, "status": "running"}
        return agent.id

    async def complete_task(self, task_id: str, result: Any = None):
        if task_id in self._tasks:
            agent_id = self._tasks[task_id]["agent"]
            agent = self._agents.get(agent_id)
            if agent: agent.complete_task()
            self._tasks[task_id]["status"] = "completed"
            self._tasks[task_id]["result"] = result

    def get_status(self) -> dict:
        return {
            "topology": self.topology,
            "agents": len(self._agents),
            "active": len([a for a in self._agents.values() if a.status == "busy"]),
            "tasks": len(self._tasks),
            "running_tasks": len([t for t in self._tasks.values() if t["status"] == "running"]),
        }
