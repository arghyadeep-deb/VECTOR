"""VECTOR's isolated, deterministic self-development tooling district."""

from districts.self_dev.self_dev_specialists import (
    AgentCreator,
    ConversationAnalyzer,
    PluginValidator,
    SkillAnalyzer,
    SkillComparator,
    SkillGrader,
    SkillReviewer,
)

__all__ = [
    "AgentCreator",
    "ConversationAnalyzer",
    "PluginValidator",
    "SkillAnalyzer",
    "SkillComparator",
    "SkillGrader",
    "SkillReviewer",
]


if __name__ == "__main__":
    instances = [globals()[name]() for name in __all__]
    assert all(agent.district == "self_dev" for agent in instances)

