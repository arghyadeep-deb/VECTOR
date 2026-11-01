"""
VectorCode Agent Registry — central access point for all vc_agents.

Lazy-init singletons for every vectorcode internal agent. VECTOR's districts
call these directly when they need vectorcode's capabilities (web search,
image gen, skill execution, routing, memory, insights, reasoning, tools).

Usage:
    from vectorcode.src.vc_agents.agent_registry import vc_agents
    results = vc_agents.web.search("AI news")
    model = vc_agents.routing.route_to_model("write python code")
    vc_agents.reasoning.store(thought, action, outcome, reward=0.9)
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger


class _VCAgentRegistry:
    """Singleton registry of all vectorcode internal agents."""

    def __init__(self):
        self._web: object | None = None
        self._image: object | None = None
        self._video: object | None = None
        self._skill: object | None = None
        self._routing: object | None = None
        self._memory: object | None = None
        self._insight: object | None = None
        self._reasoning: object | None = None
        self._tool: object | None = None

    @property
    def web(self):
        """WebSearchAgent — search + extract via vectorcode's provider registry."""
        if self._web is None:
            from vectorcode.src.vc_agents.web_search_agent import WebSearchAgent
            self._web = WebSearchAgent()
        return self._web

    @property
    def image(self):
        """ImageAgent — AI image generation via registered backends."""
        if self._image is None:
            from vectorcode.src.vc_agents.image_agent import ImageAgent
            self._image = ImageAgent()
        return self._image

    @property
    def video(self):
        """VideoAgent — AI video generation via registered backends."""
        if self._video is None:
            from vectorcode.src.vc_agents.video_agent import VideoAgent
            self._video = VideoAgent()
        return self._video

    @property
    def skill(self):
        """SkillAgent — loads and executes skill .md files."""
        if self._skill is None:
            from vectorcode.src.vc_agents.skill_agent import SkillAgent
            self._skill = SkillAgent()
        return self._skill

    @property
    def routing(self):
        """RoutingAgent — model + district selection using GNNRouter."""
        if self._routing is None:
            from vectorcode.src.vc_agents.routing_agent import RoutingAgent
            self._routing = RoutingAgent()
        return self._routing

    @property
    def memory(self):
        """MemoryAgent — session memory bridging vc MemoryManager + VECTOR episodic."""
        if self._memory is None:
            from vectorcode.src.vc_agents.memory_agent import MemoryAgent
            self._memory = MemoryAgent()
        return self._memory

    @property
    def insight(self):
        """InsightAgent — usage analytics from InsightsEngine + episodic memory."""
        if self._insight is None:
            from vectorcode.src.vc_agents.insight_agent import InsightAgent
            self._insight = InsightAgent()
        return self._insight

    @property
    def reasoning(self):
        """ReasoningAgent — RULE 8: stores/injects reasoning chains via ReasoningBank."""
        if self._reasoning is None:
            from vectorcode.src.vc_agents.reasoning_agent import ReasoningAgent
            self._reasoning = ReasoningAgent()
        return self._reasoning

    @property
    def tool(self):
        """ToolAgent — safe tool execution via ToolCallGuardrailController."""
        if self._tool is None:
            from vectorcode.src.vc_agents.tool_agent import ToolAgent
            self._tool = ToolAgent()
        return self._tool

    @property
    def brain_agents(self) -> dict[str, dict]:
        """Load all brain/.claude/agents/*.md as callable agent definitions."""
        if not hasattr(self, '_brain_agents_cache'):
            brain_agents: dict[str, dict] = {}
            brain_dir = Path.home() / "V.E.C.T.O.R Brain" / ".claude" / "agents"
            fallback_dir = Path(__file__).parent.parent.parent.parent / "brain" / ".claude" / "agents"

            for agents_dir in [brain_dir, fallback_dir]:
                if agents_dir.exists():
                    for md_file in agents_dir.glob("**/*.md"):
                        name = md_file.stem
                        try:
                            content = md_file.read_text(encoding="utf-8", errors="ignore")
                        except Exception:
                            content = ""
                        description = ""
                        # Extract description from frontmatter
                        if "description:" in content[:500]:
                            for line in content[:500].splitlines():
                                if line.strip().startswith("description:"):
                                    description = line.split(":", 1)[1].strip().strip('"\'')
                                    break
                        brain_agents[name] = {
                            "name": name,
                            "description": description or f"Brain agent: {name}",
                            "path": str(md_file),
                            "content": content[:5000],
                        }
                    break  # use first found directory

            self._brain_agents_cache = brain_agents
            logger.info("[VECTOR][vc_agents] Loaded {} brain agents", len(brain_agents))

        return self._brain_agents_cache

    def status(self) -> dict:
        """Return which agents are initialized."""
        return {
            "web":       self._web is not None,
            "image":     self._image is not None,
            "video":     self._video is not None,
            "skill":     self._skill is not None,
            "routing":   self._routing is not None,
            "memory":    self._memory is not None,
            "insight":   self._insight is not None,
            "reasoning": self._reasoning is not None,
            "tool":      self._tool is not None,
        }

    def warm_all(self) -> dict:
        """Pre-initialize all agents (optional — they init lazily by default)."""
        _ = self.web, self.image, self.video, self.skill, self.routing
        _ = self.memory, self.insight, self.reasoning, self.tool
        s = self.status()
        logger.info("[VECTOR][vc_registry] warmed {}/{} vc_agents", sum(s.values()), len(s))
        return s


# Module-level singleton — import and use directly
vc_agents = _VCAgentRegistry()


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    # Verify all agents initialize without error
    registry = _VCAgentRegistry()
    names = ["web", "image", "video", "skill", "routing", "memory", "insight", "reasoning", "tool"]
    for name in names:
        try:
            agent = getattr(registry, name)
            print(f"[OK] {name}: {type(agent).__name__}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

    status = registry.status()
    initialized = sum(status.values())
    print(f"\n[OK] registry: {initialized}/{len(status)} vc_agents initialized")
    print("agent_registry.py OK")
