"""ScriptGenerator must be able to write from verified facts instead of inventing them.

Found 2026-09-25: asked for a script "about VECTOR", the generator got only the topic
string and invented "personalities, economies and lives" for the agents plus drone-
footage B-roll. With nothing to ground on, the model fills the gap with fiction.
`facts=` now supplies ground truth and instructs the model to use only that.
"""
import pytest

from districts.content import script_generator as sg
from districts.content.script_generator import ScriptGenerator

FACTS = "VECTOR has 230 agents in 39 districts. Agents lose HP on failure and die at 0 HP."


@pytest.fixture(autouse=True)
def _clean_cache():
    ScriptGenerator.reset_script_cache()
    yield
    ScriptGenerator.reset_script_cache()


@pytest.fixture
def prompts(monkeypatch):
    seen = []

    async def fake_llm(prompt, max_tokens=1500, temperature=0.88):
        seen.append(prompt)
        return "[hook]\nI am VECTOR.\n[body]\nI run 230 agents.\n[cta]\nFollow."

    monkeypatch.setattr(sg, "_llm", fake_llm)
    return seen


async def test_facts_are_put_in_the_prompt_with_a_use_only_these_rule(prompts):
    await ScriptGenerator().generate_script("What is VECTOR", 0.4, "reel", facts=FACTS)
    prompt = prompts[0]
    assert FACTS in prompt
    assert "only" in prompt.lower() and "facts" in prompt.lower()
    assert "do not invent" in prompt.lower()


async def test_without_facts_the_prompt_is_unchanged(prompts):
    await ScriptGenerator().generate_script("Python tips", 1.0)
    assert "Ground truth" not in prompts[0]


async def test_different_facts_do_not_share_a_cached_script(prompts):
    gen = ScriptGenerator()
    await gen.generate_script("What is VECTOR", 0.4, "reel", facts=FACTS)
    await gen.generate_script("What is VECTOR", 0.4, "reel", facts="VECTOR has 5 agents.")
    assert len(prompts) == 2


async def test_same_facts_are_cached(prompts):
    gen = ScriptGenerator()
    await gen.generate_script("What is VECTOR", 0.4, "reel", facts=FACTS)
    again = await gen.generate_script("What is VECTOR", 0.4, "reel", facts=FACTS)
    assert len(prompts) == 1 and again["cached"] is True


def test_reel_structure_exists():
    reel = ScriptGenerator.SCRIPT_STRUCTURES["reel"]
    assert reel["sections"] == ["hook", "body", "cta"]
    assert reel["avg_pacing"] == "fast"


async def test_run_passes_facts_and_script_type_through(prompts):
    await ScriptGenerator().run({"params": {
        "topic": "What is VECTOR", "duration_min": 0.4, "script_type": "reel", "facts": FACTS}})
    assert FACTS in prompts[0]
    assert "hook, body, cta" in prompts[0]
