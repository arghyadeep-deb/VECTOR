"""
vectorcode/src/neural_training/__init__.py
VECTOR Neural Training package — drop-in replacement for neural_training.py.
"""
from ._trainer import (
    A2C, A2CConfig,
    DQN, DQNConfig,
    PPO, PPOConfig,
    SARSA, SARSAConfig,
    QLearning, QLearningConfig,
    DecisionTransformer,
    CuriosityModule,
    VECTORTrainer,
    TrainingStats,
    _softmax, _relu, _linear,
)

__all__ = [
    "A2C", "A2CConfig", "DQN", "DQNConfig", "PPO", "PPOConfig",
    "SARSA", "SARSAConfig", "QLearning", "QLearningConfig",
    "DecisionTransformer", "CuriosityModule", "VECTORTrainer", "TrainingStats",
    "_softmax", "_relu", "_linear",
]
