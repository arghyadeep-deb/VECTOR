"""
VECTOR Social Simulation Engine — core/vector_social_sim

Swarm intelligence platform for social dynamics prediction.
Provides:
- Document → Ontology extraction (LLM-driven entity/relationship types)
- Zep Cloud knowledge graph construction (semantic + temporal)
- Agent persona generation from graph entities (psychological profiles)
- OASIS dual-platform simulation (Twitter 6 actions + Reddit 10 actions)
- Intelligent simulation config generation (activity patterns, sentiment, stance)
- ReACT report agent (InsightForge/PanoramaSearch/QuickSearch tools)
- Interactive agent interviews post-simulation

Usage via VECTOR governor:
  social_simulate, build_ontology, build_graph, generate_personas,
  simulation_report, agent_interview

Requires: LLM_API_KEY (or OPENAI_API_KEY), ZEP_API_KEY in .env
"""
import sys
from pathlib import Path

# Add core/vector_social_sim/ to sys.path so all "from app.X" imports resolve
_SOCIAL_SIM_DIR = Path(__file__).resolve().parent
if str(_SOCIAL_SIM_DIR) not in sys.path:
    sys.path.insert(0, str(_SOCIAL_SIM_DIR))
