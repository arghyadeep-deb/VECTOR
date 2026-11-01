"""Continuous RL trainer: simplified PPO/A2C for in-loop policy improvement."""

from typing import Any

from loguru import logger

try:
    import numpy as np
except ImportError:
    logger.warning("[Training] numpy not available, RL trainer disabled")
    np = None


class ContinuousRLTrainer:
    def __init__(self, learning_rate: float = 0.01, gamma: float = 0.99, clip_epsilon: float = 0.2):
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.clip_epsilon = clip_epsilon
        self.experience_buffer: list[dict] = []
        self.min_experience_for_train = 32
        self.batch_size = 16
        self._policy_params: dict[str, float] = {"temperature": 0.7, "top_p": 0.9, "top_k": 40}
        self._step_count = 0
        logger.info("[Training] ContinuousRLTrainer initialized (lr={}, gamma={})", learning_rate, gamma)

    def collect_experience(self, state_buffer: list[dict]) -> list[dict]:
        collected = []
        for state in state_buffer:
            action = state.get("action", "")
            reward = float(state.get("reward", 0.0))
            context = state.get("context", "")
            state_repr = state.get("state", context)
            if action and reward != 0.0:
                experience = {
                    "state": state_repr,
                    "action": action,
                    "reward": reward,
                    "timestamp": state.get("timestamp", ""),
                    "task_type": state.get("task_type", "general"),
                }
                collected.append(experience)
        self.experience_buffer.extend(collected)
        if len(self.experience_buffer) > 10000:
            self.experience_buffer = self.experience_buffer[-5000:]
        if collected:
            logger.info("[Training] Collected {} experiences (buffer: {})", len(collected), len(self.experience_buffer))
        return collected

    def train_step(self, batch: list[dict]) -> dict:
        if np is None:
            logger.warning("[Training] numpy required for RL training, skipping")
            return {"status": "skipped", "reason": "numpy_not_available"}
        if not batch:
            return {"status": "skipped", "reason": "empty_batch"}
        actions = []
        rewards = []
        for exp in batch:
            actions.append(exp.get("action", ""))
            rewards.append(float(exp.get("reward", 0.0)))
        rewards_arr = np.array(rewards, dtype=np.float32)
        discounted = self._compute_discounted_returns(rewards_arr)
        advantage = discounted - np.mean(discounted)
        if np.std(discounted) > 1e-8:
            advantage = advantage / (np.std(discounted) + 1e-8)
        reward_mean = float(np.mean(rewards_arr))
        reward_std = float(np.std(rewards_arr))
        if reward_mean > 0:
            self._policy_params["temperature"] = max(0.3, self._policy_params["temperature"] * 0.99)
        else:
            self._policy_params["temperature"] = min(1.5, self._policy_params["temperature"] * 1.01)
        if abs(float(np.mean(advantage))) > 0.1:
            clip_scale = 1.0 + self.clip_epsilon * float(np.mean(advantage))
            self._policy_params["top_p"] = max(0.5, min(1.0, self._policy_params["top_p"] * clip_scale))
        self._step_count += 1
        logger.info("[Training] RL step {}: reward={:.4f}±{:.4f}, temp={:.3f}, top_p={:.3f}",
                     self._step_count, reward_mean, reward_std,
                     self._policy_params["temperature"], self._policy_params["top_p"])
        return {
            "status": "success",
            "step": self._step_count,
            "batch_size": len(batch),
            "reward_mean": round(reward_mean, 4),
            "reward_std": round(reward_std, 4),
            "advantage_mean": round(float(np.mean(advantage)), 4),
            "policy_update": dict(self._policy_params),
        }

    def get_policy_update(self) -> dict:
        return {
            "step": self._step_count,
            "buffer_size": len(self.experience_buffer),
            "parameters": dict(self._policy_params),
            "suggested_changes": {
                "temperature": self._policy_params["temperature"],
                "top_p": self._policy_params["top_p"],
                "top_k": self._policy_params["top_k"],
            },
        }

    def should_train(self) -> bool:
        ready = len(self.experience_buffer) >= self.min_experience_for_train
        if ready:
            logger.info("[Training] Buffer has {} experiences, ready to train", len(self.experience_buffer))
        return ready

    def _compute_discounted_returns(self, rewards: np.ndarray) -> np.ndarray:
        returns = np.zeros_like(rewards)
        cumulative = 0.0
        for i in range(len(rewards) - 1, -1, -1):
            cumulative = rewards[i] + self.gamma * cumulative
            returns[i] = cumulative
        return returns
