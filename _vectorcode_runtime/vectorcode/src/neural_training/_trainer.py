"""
vectorcode/src/neural_training/_trainer.py
RL training algorithms loaded from the canonical neural_training.py monolith.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

_MONOLITH_KEY = "_vector_neural_training_monolith"

if _MONOLITH_KEY not in sys.modules:
    _monolith_path = Path(__file__).parent.parent / "neural_training.py"
    _spec = importlib.util.spec_from_file_location(_MONOLITH_KEY, str(_monolith_path))
    assert _spec is not None, f"Could not load {_monolith_path}"
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_MONOLITH_KEY] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_mod = sys.modules[_MONOLITH_KEY]

A2C = _mod.A2C
A2CConfig = _mod.A2CConfig
DQN = _mod.DQN
DQNConfig = _mod.DQNConfig
PPO = _mod.PPO
PPOConfig = _mod.PPOConfig
SARSA = _mod.SARSA
SARSAConfig = _mod.SARSAConfig
QLearning = _mod.QLearning
QLearningConfig = _mod.QLearningConfig
DecisionTransformer = _mod.DecisionTransformer
CuriosityModule = _mod.CuriosityModule
VECTORTrainer = _mod.VECTORTrainer
TrainingStats = _mod.TrainingStats
_softmax = _mod._softmax
_relu = _mod._relu
_linear = _mod._linear
fake_batch = getattr(_mod, "fake_batch", None)  # only exists in __main__ block

__all__ = [
    "A2C", "A2CConfig", "DQN", "DQNConfig", "PPO", "PPOConfig",
    "SARSA", "SARSAConfig", "QLearning", "QLearningConfig",
    "DecisionTransformer", "CuriosityModule", "VECTORTrainer", "TrainingStats",
    "_softmax", "_relu", "_linear",
]
