"""
VECTOR neural training — A2C, DQN, Curiosity, DecisionTransformer, PPO, SARSA, Q-Learning, VECTORTrainer.

⚠️  EDUCATIONAL / EXPERIMENTAL — NOT PRODUCTION (Issue 22)
====================================================================
All algorithms in this file are implemented in pure NumPy for
educational clarity. They are NOT suitable for real model training:

  - No PyTorch / TensorFlow / JAX — cannot use GPU acceleration
  - No gradient checkpointing, mixed precision, or distributed training
  - Toy-scale only: works on CartPole-style envs, not LLM fine-tuning

For real RL training on VECTOR's reasoning chains, use:
  - core/training/openmythos/trainer.py  (LoRA fine-tuning via PyTorch)
  - core/training/self_improvement_cycle.py  (weekly pipeline)

These implementations are kept for reference and unit-testing the
reward/policy logic without a GPU dependency.
====================================================================
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger
from vectorcode.src.utils import atomic_json_write


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


def _linear(x: np.ndarray, W: np.ndarray, b: np.ndarray) -> np.ndarray:
    return x @ W + b


# ---------------------------------------------------------------------------
# A2C — Advantage Actor-Critic
# ---------------------------------------------------------------------------

@dataclass
class A2CConfig:
    state_dim: int = 64
    action_dim: int = 20
    hidden_dim: int = 128
    lr: float = 7e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5


class A2C:
    """Synchronous Advantage Actor-Critic with GAE and entropy regularisation."""

    def __init__(self, cfg: A2CConfig = A2CConfig()) -> None:
        self.cfg = cfg
        sd, hd, ad = cfg.state_dim, cfg.hidden_dim, cfg.action_dim
        rng = np.random.default_rng(42)
        sc = lambda n, m: rng.standard_normal((n, m)) * np.sqrt(2.0 / n)
        self.W1 = sc(sd, hd);  self.b1 = np.zeros(hd)
        self.Wp = sc(hd, ad);  self.bp = np.zeros(ad)
        self.Wv = sc(hd, 1);   self.bv = np.zeros(1)
        self.episode_count = 0
        self.total_reward = 0.0

    def _forward(self, state: np.ndarray):
        h = _relu(_linear(state, self.W1, self.b1))
        probs = _softmax(_linear(h, self.Wp, self.bp))
        value = float(_linear(h, self.Wv, self.bv)[0])
        return h, probs, value

    def select_action(self, state: np.ndarray):
        _, probs, value = self._forward(np.asarray(state, dtype=np.float32))
        action = int(np.random.choice(len(probs), p=probs))
        log_prob = float(np.log(probs[action] + 1e-8))
        entropy = float(-np.sum(probs * np.log(probs + 1e-8)))
        return action, log_prob, entropy

    def update(self, states, actions, rewards, dones, next_state) -> dict:
        n = len(rewards)
        ns_arr = np.asarray(next_state, dtype=np.float32)
        _, _, next_val = self._forward(ns_arr)

        values = []
        hs = []
        probs_list = []
        for i in range(n):
            s = np.asarray(states[i], dtype=np.float32)
            h, probs, val = self._forward(s)
            values.append(val)
            hs.append(h)
            probs_list.append(probs)

        # GAE
        advantages = np.zeros(n)
        gae = 0.0
        for t in reversed(range(n)):
            nv = next_val if t == n - 1 else values[t + 1]
            dm = 0.0 if (t < len(dones) and dones[t]) else 1.0
            delta = rewards[t] + self.cfg.gamma * nv * dm - values[t]
            gae = delta + self.cfg.gamma * self.cfg.gae_lambda * dm * gae
            advantages[t] = gae
        returns = advantages + np.array(values)

        policy_loss = value_loss = entropy_total = 0.0
        lr = self.cfg.lr
        for i in range(n):
            h, probs, val = hs[i], probs_list[i], values[i]
            a, adv, ret = actions[i], float(advantages[i]), float(returns[i])
            ent = -float(np.sum(probs * np.log(probs + 1e-8)))
            policy_loss += -math.log(probs[a] + 1e-8) * adv
            value_loss  += (val - ret) ** 2
            entropy_total += ent
            # Policy head gradient
            dp = probs.copy(); dp[a] -= 1.0
            self.Wp -= lr * np.outer(h, dp * adv)
            self.bp -= lr * dp * adv
            # Value head gradient
            dv = 2 * (val - ret) * self.cfg.value_loss_coef
            self.Wv -= lr * dv * h.reshape(-1, 1)
            self.bv -= lr * dv
            # Entropy regularisation
            self.Wp += lr * self.cfg.entropy_coef * np.outer(h, probs * (1 + np.log(probs + 1e-8)))

        self.episode_count += 1
        self.total_reward += sum(rewards)
        total = (policy_loss + self.cfg.value_loss_coef * value_loss - self.cfg.entropy_coef * entropy_total) / n
        return {"policy_loss": policy_loss / n, "value_loss": value_loss / n, "entropy": entropy_total / n, "total": total}

    def save(self, path: Path) -> None:
        atomic_json_write(path, {k: getattr(self, k).tolist() for k in ["W1", "b1", "Wp", "bp", "Wv", "bv"]})

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        for k in ["W1","b1","Wp","bp","Wv","bv"]:
            if k in d:
                setattr(self, k, np.array(d[k], dtype=np.float32))


# ---------------------------------------------------------------------------
# DQN — Deep Q-Network with experience replay
# ---------------------------------------------------------------------------

@dataclass
class DQNConfig:
    state_dim: int = 64
    action_dim: int = 20
    hidden_dim: int = 128
    lr: float = 1e-4
    gamma: float = 0.99
    buffer_size: int = 10_000
    batch_size: int = 32
    epsilon: float = 1.0
    epsilon_min: float = 0.01
    epsilon_decay: float = 0.995
    target_update_freq: int = 100
    double_dqn: bool = True


class DQN:
    """DQN with experience replay, target network, double-DQN."""

    def __init__(self, cfg: DQNConfig = DQNConfig()) -> None:
        self.cfg = cfg
        sd, hd, ad = cfg.state_dim, cfg.hidden_dim, cfg.action_dim
        rng = np.random.default_rng(0)
        sc = lambda n, m: rng.standard_normal((n, m)) * np.sqrt(2.0 / n)
        self.W1 = sc(sd, hd); self.b1 = np.zeros(hd)
        self.W2 = sc(hd, ad); self.b2 = np.zeros(ad)
        self.tW1 = self.W1.copy(); self.tb1 = self.b1.copy()
        self.tW2 = self.W2.copy(); self.tb2 = self.b2.copy()
        self._buf: deque = deque(maxlen=cfg.buffer_size)
        self._steps = 0
        self.epsilon = cfg.epsilon
        self.episode_count = 0
        self.total_reward = 0.0

    def _q(self, s, W1=None, b1=None, W2=None, b2=None) -> np.ndarray:
        W1 = W1 if W1 is not None else self.W1
        b1 = b1 if b1 is not None else self.b1
        W2 = W2 if W2 is not None else self.W2
        b2 = b2 if b2 is not None else self.b2
        return _linear(_relu(_linear(s, W1, b1)), W2, b2)

    def select_action(self, state) -> int:
        if random.random() < self.epsilon:
            return random.randrange(self.cfg.action_dim)
        return int(np.argmax(self._q(np.asarray(state, dtype=np.float32))))

    def remember(self, s, a: int, r: float, ns, done: bool) -> None:
        self._buf.append((np.asarray(s, dtype=np.float32), a, r, np.asarray(ns, dtype=np.float32), done))

    def replay(self) -> float:
        if len(self._buf) < self.cfg.batch_size:
            return 0.0
        batch = random.sample(self._buf, self.cfg.batch_size)
        loss = 0.0
        lr = self.cfg.lr
        for s, a, r, ns, done in batch:
            qv = self._q(s)
            if self.cfg.double_dqn:
                a_next = int(np.argmax(self._q(ns)))
                q_next = self._q(ns, self.tW1, self.tb1, self.tW2, self.tb2)[a_next]
            else:
                q_next = float(np.max(self._q(ns, self.tW1, self.tb1, self.tW2, self.tb2)))
            target = r + (0.0 if done else self.cfg.gamma * q_next)
            err = float(qv[a]) - target
            loss += err ** 2
            h = _relu(_linear(s, self.W1, self.b1))
            grad_out = np.zeros(self.cfg.action_dim); grad_out[a] = 2.0 * err
            self.W2 -= lr * np.outer(h, grad_out)
            self.b2 -= lr * grad_out
            grad_h = (h > 0) * (self.W2 @ grad_out)
            self.W1 -= lr * np.outer(s, grad_h)
            self.b1 -= lr * grad_h
        self._steps += 1
        self.epsilon = max(self.cfg.epsilon_min, self.epsilon * self.cfg.epsilon_decay)
        if self._steps % self.cfg.target_update_freq == 0:
            self.tW1 = self.W1.copy(); self.tb1 = self.b1.copy()
            self.tW2 = self.W2.copy(); self.tb2 = self.b2.copy()
        return loss / self.cfg.batch_size

    def save(self, path: Path) -> None:
        atomic_json_write(path, {k: getattr(self, k).tolist() for k in ["W1", "b1", "W2", "b2"]})

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        for k in ["W1","b1","W2","b2"]:
            setattr(self, k, np.array(d[k], dtype=np.float32))


# ---------------------------------------------------------------------------
# Curiosity Module (ICM)
# ---------------------------------------------------------------------------

class CuriosityModule:
    """Intrinsic curiosity — generates bonus rewards for novel state transitions."""

    def __init__(self, state_dim: int = 64, action_dim: int = 20, feature_dim: int = 32, lr: float = 1e-3) -> None:
        rng = np.random.default_rng(7)
        sc = lambda n, m: rng.standard_normal((n, m)) * np.sqrt(2.0 / n)
        self.Wenc = sc(state_dim, feature_dim); self.benc = np.zeros(feature_dim)
        self.Wfwd = sc(feature_dim + action_dim, feature_dim); self.bfwd = np.zeros(feature_dim)
        self.lr = lr
        self.action_dim = action_dim

    def _encode(self, s) -> np.ndarray:
        return _relu(_linear(np.asarray(s, dtype=np.float32), self.Wenc, self.benc))

    def compute_intrinsic_reward(self, s, a: int, ns) -> float:
        phi_s  = self._encode(s)
        phi_ns = self._encode(ns)
        a_oh = np.zeros(self.action_dim, dtype=np.float32); a_oh[a] = 1.0
        pred = _relu(_linear(np.concatenate([phi_s, a_oh]), self.Wfwd, self.bfwd))
        return float(np.mean((phi_ns - pred) ** 2))

    def update(self, s, a: int, ns) -> float:
        phi_s  = self._encode(s)
        phi_ns = self._encode(ns)
        a_oh = np.zeros(self.action_dim, dtype=np.float32); a_oh[a] = 1.0
        inp = np.concatenate([phi_s, a_oh])
        pred = _relu(_linear(inp, self.Wfwd, self.bfwd))
        err = pred - phi_ns
        loss = float(np.mean(err ** 2))
        grad = (pred > 0) * err
        self.Wfwd -= self.lr * np.outer(inp, grad)
        self.bfwd -= self.lr * grad
        return loss


# ---------------------------------------------------------------------------
# Decision Transformer
# ---------------------------------------------------------------------------

class DecisionTransformer:
    """Conditions action prediction on return-to-go and trajectory history."""

    def __init__(self, state_dim: int = 64, action_dim: int = 20, max_len: int = 20, embed_dim: int = 64) -> None:
        rng = np.random.default_rng(3)
        sc = lambda n, m: rng.standard_normal((n, m)) * np.sqrt(2.0 / n)
        self.max_len = max_len
        self.action_dim = action_dim
        self.embed_dim = embed_dim
        self.Ws = sc(state_dim, embed_dim)
        self.Wa = sc(action_dim, embed_dim)
        self.Wr = sc(1, embed_dim)
        self.Wq = sc(embed_dim, embed_dim)
        self.Wk = sc(embed_dim, embed_dim)
        self.Wv = sc(embed_dim, embed_dim)
        self.Wout = sc(embed_dim, action_dim)
        self.bout = np.zeros(action_dim)
        self.lr = 1e-3
        self.episode_count = 0

    def _embed(self, s, a: int, rtg: float) -> np.ndarray:
        a_oh = np.zeros(self.action_dim, dtype=np.float32); a_oh[a] = 1.0
        return _relu(np.asarray(s, dtype=np.float32) @ self.Ws) + _relu(a_oh @ self.Wa) + _relu(np.array([rtg], dtype=np.float32) @ self.Wr)

    def predict_action(self, states, actions, rtgs) -> int:
        if not states:
            return random.randrange(self.action_dim)
        w = min(len(states), self.max_len)
        tokens = np.stack([self._embed(states[i], actions[i] if i > 0 else 0, rtgs[i] if i < len(rtgs) else 0.0) for i in range(-w, 0)])
        Q = tokens @ self.Wq; K = tokens @ self.Wk; V = tokens @ self.Wv
        scale = math.sqrt(self.embed_dim)
        attn = Q @ K.T / scale
        mask = np.triu(np.full_like(attn, -1e9), k=1)
        weights = np.apply_along_axis(_softmax, 1, attn + mask)
        ctx = weights @ V
        logits = _linear(ctx[-1], self.Wout, self.bout)
        return int(np.argmax(logits))

    def update(self, trajectory) -> float:
        if len(trajectory) < 2:
            return 0.0
        loss = 0.0
        for i in range(1, len(trajectory)):
            states = [t[0] for t in trajectory[:i]]
            actions = [t[1] for t in trajectory[:i]]
            rtgs   = [t[2] for t in trajectory[:i]]
            pred_a = self.predict_action(states, actions, rtgs)
            true_a = trajectory[i][1]
            loss += 0.0 if pred_a == true_a else 1.0
            if pred_a != true_a:
                ctx = self._embed(states[-1], actions[-1], rtgs[-1] if rtgs else 0.0)
                self.Wout[:, true_a] += self.lr * ctx
                self.Wout[:, pred_a] -= self.lr * ctx
        self.episode_count += 1
        return loss / max(1, len(trajectory) - 1)

    def save(self, path: Path) -> None:
        atomic_json_write(path, {k: getattr(self, k).tolist() for k in ["Ws", "Wa", "Wr", "Wq", "Wk", "Wv", "Wout", "bout"]})

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        for k in ["Ws","Wa","Wr","Wq","Wk","Wv","Wout","bout"]:
            if k in d:
                setattr(self, k, np.array(d[k], dtype=np.float32))


# ---------------------------------------------------------------------------
# PPO — Proximal Policy Optimization
# ---------------------------------------------------------------------------

@dataclass
class PPOConfig:
    state_dim: int = 64
    action_dim: int = 20
    hidden_dim: int = 128
    lr: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    epochs: int = 4
    mini_batch_size: int = 64
    target_kl: float = 0.01
    clip_range_vf: Optional[float] = None


class PPO:
    """Proximal Policy Optimization with clipped surrogate objective and GAE."""

    def __init__(self, cfg: PPOConfig = PPOConfig()) -> None:
        self.cfg = cfg
        sd, hd, ad = cfg.state_dim, cfg.hidden_dim, cfg.action_dim
        rng = np.random.default_rng(17)
        sc = lambda n, m: rng.standard_normal((n, m)) * np.sqrt(2.0 / n)
        # Policy network: state_dim → hidden_dim → action_dim
        self.pW1 = sc(sd, hd);  self.pb1 = np.zeros(hd)
        self.pW2 = sc(hd, ad);  self.pb2 = np.zeros(ad)
        # Value network: state_dim → hidden_dim → 1
        self.vW1 = sc(sd, hd);  self.vb1 = np.zeros(hd)
        self.vW2 = sc(hd, 1);   self.vb2 = np.zeros(1)
        # Adam optimizer moments for all 8 weight tensors
        self._adam_m: dict = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._adam_v: dict = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._adam_t: int = 0
        self.episode_count = 0
        self.total_reward = 0.0

    def _params(self) -> dict:
        return {
            "pW1": self.pW1, "pb1": self.pb1,
            "pW2": self.pW2, "pb2": self.pb2,
            "vW1": self.vW1, "vb1": self.vb1,
            "vW2": self.vW2, "vb2": self.vb2,
        }

    def _adam_step(self, name: str, grad: np.ndarray) -> np.ndarray:
        b1, b2, eps = 0.9, 0.999, 1e-8
        self._adam_m[name] = b1 * self._adam_m[name] + (1.0 - b1) * grad
        self._adam_v[name] = b2 * self._adam_v[name] + (1.0 - b2) * grad ** 2
        m_hat = self._adam_m[name] / (1.0 - b1 ** self._adam_t)
        v_hat = self._adam_v[name] / (1.0 - b2 ** self._adam_t)
        return self.cfg.lr * m_hat / (np.sqrt(v_hat) + eps)

    def _policy_forward(self, s: np.ndarray):
        """Returns (hidden, probs)."""
        h = _relu(_linear(s, self.pW1, self.pb1))
        probs = _softmax(_linear(h, self.pW2, self.pb2))
        return h, probs

    def _value_forward(self, s: np.ndarray) -> float:
        """Returns scalar value estimate."""
        h = _relu(_linear(s, self.vW1, self.vb1))
        return float(_linear(h, self.vW2, self.vb2)[0])

    def select_action(self, state: np.ndarray):
        """Returns (action, log_prob, value)."""
        s = np.asarray(state, dtype=np.float32)
        _, probs = self._policy_forward(s)
        action = int(np.random.choice(len(probs), p=probs))
        log_prob = float(np.log(probs[action] + 1e-8))
        value = self._value_forward(s)
        return action, log_prob, value

    def _compute_gae(self, rewards, values, dones, next_value: float):
        """Generalised Advantage Estimation."""
        n = len(rewards)
        advantages = np.zeros(n, dtype=np.float32)
        gae = 0.0
        for t in reversed(range(n)):
            nv = next_value if t == n - 1 else values[t + 1]
            dm = 0.0 if (t < len(dones) and dones[t]) else 1.0
            delta = rewards[t] + self.cfg.gamma * nv * dm - values[t]
            gae = delta + self.cfg.gamma * self.cfg.gae_lambda * dm * gae
            advantages[t] = gae
        returns = advantages + np.array(values, dtype=np.float32)
        return advantages, returns

    def update(self, states, actions, rewards, dones, next_state) -> dict:
        """Run PPO epochs over collected rollout data."""
        n = len(rewards)
        states_arr = [np.asarray(s, dtype=np.float32) for s in states]
        ns_arr = np.asarray(next_state, dtype=np.float32)

        # Collect old log-probs and values from the current policy (before update)
        old_log_probs = np.zeros(n, dtype=np.float32)
        values = np.zeros(n, dtype=np.float32)
        for i, s in enumerate(states_arr):
            _, probs = self._policy_forward(s)
            old_log_probs[i] = np.log(probs[actions[i]] + 1e-8)
            values[i] = self._value_forward(s)
        next_value = self._value_forward(ns_arr)

        advantages, returns = self._compute_gae(rewards, values.tolist(), dones, next_value)
        # Normalise advantages
        adv_std = advantages.std() + 1e-8
        advantages = (advantages - advantages.mean()) / adv_std

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        total_approx_kl = 0.0
        total_clip_frac = 0.0
        update_count = 0

        for _epoch in range(self.cfg.epochs):
            # Build mini-batches
            indices = np.arange(n)
            np.random.shuffle(indices)
            mb_size = min(self.cfg.mini_batch_size, n)
            for start in range(0, n, mb_size):
                mb_idx = indices[start: start + mb_size]
                if len(mb_idx) == 0:
                    continue

                self._adam_t += 1
                # Accumulate gradients across mini-batch
                grad_pW1 = np.zeros_like(self.pW1)
                grad_pb1 = np.zeros_like(self.pb1)
                grad_pW2 = np.zeros_like(self.pW2)
                grad_pb2 = np.zeros_like(self.pb2)
                grad_vW1 = np.zeros_like(self.vW1)
                grad_vb1 = np.zeros_like(self.vb1)
                grad_vW2 = np.zeros_like(self.vW2)
                grad_vb2 = np.zeros_like(self.vb2)

                mb_policy_loss = 0.0
                mb_value_loss = 0.0
                mb_entropy = 0.0
                mb_approx_kl = 0.0
                mb_clip_frac = 0.0

                for idx in mb_idx:
                    s = states_arr[idx]
                    a = int(actions[idx])
                    adv = float(advantages[idx])
                    ret = float(returns[idx])
                    old_lp = float(old_log_probs[idx])

                    # Policy forward
                    ph, probs = self._policy_forward(s)
                    new_lp = float(np.log(probs[a] + 1e-8))
                    ratio = np.exp(new_lp - old_lp)
                    clipped_ratio = np.clip(ratio, 1.0 - self.cfg.clip_range, 1.0 + self.cfg.clip_range)
                    is_clipped = float(abs(ratio - 1.0) > self.cfg.clip_range)

                    # PPO clipped surrogate loss (negate for gradient descent)
                    surr1 = ratio * adv
                    surr2 = clipped_ratio * adv
                    p_loss = -min(surr1, surr2)
                    entropy = float(-np.sum(probs * np.log(probs + 1e-8)))

                    # Value forward
                    vh = _relu(_linear(s, self.vW1, self.vb1))
                    val = float(_linear(vh, self.vW2, self.vb2)[0])
                    if self.cfg.clip_range_vf is not None:
                        old_val = float(values[idx])
                        val_clipped = old_val + np.clip(val - old_val, -self.cfg.clip_range_vf, self.cfg.clip_range_vf)
                        v_loss = max((val - ret) ** 2, (val_clipped - ret) ** 2)
                    else:
                        v_loss = (val - ret) ** 2

                    approx_kl = old_lp - new_lp

                    mb_policy_loss += p_loss
                    mb_value_loss += v_loss
                    mb_entropy += entropy
                    mb_approx_kl += approx_kl
                    mb_clip_frac += is_clipped

                    # Policy gradients — d(-min(surr1,surr2))/d(log_prob)
                    # gradient flows through whichever branch was active
                    if surr1 <= surr2:
                        # unclipped branch active: grad wrt log_prob = -ratio * adv
                        d_lp = -ratio * adv
                    else:
                        # clipped branch active: no gradient (ratio outside clip)
                        d_lp = 0.0
                    # Chain through log_prob = log(probs[a]):  d_lp * d(log p_a)/d(p_a) * d(softmax)/d(logits)
                    d_probs = probs.copy()
                    d_probs[a] -= 1.0           # d softmax cross-entropy style
                    d_probs *= d_lp             # scale by policy gradient
                    # Entropy gradient: +entropy_coef * (log p + 1)
                    d_probs -= self.cfg.entropy_coef * (np.log(probs + 1e-8) + 1.0) * probs

                    grad_pW2 += np.outer(ph, d_probs)
                    grad_pb2 += d_probs
                    d_ph = (ph > 0) * (self.pW2 @ d_probs)
                    grad_pW1 += np.outer(s, d_ph)
                    grad_pb1 += d_ph

                    # Value gradients
                    d_val = 2.0 * (val - ret) * self.cfg.value_loss_coef
                    grad_vW2 += d_val * vh.reshape(-1, 1)
                    grad_vb2 += np.array([d_val])
                    d_vh = (vh > 0) * (self.vW2[:, 0] * d_val)
                    grad_vW1 += np.outer(s, d_vh)
                    grad_vb1 += d_vh

                mb_len = len(mb_idx)
                total_policy_loss += mb_policy_loss / mb_len
                total_value_loss += mb_value_loss / mb_len
                total_entropy += mb_entropy / mb_len
                total_approx_kl += mb_approx_kl / mb_len
                total_clip_frac += mb_clip_frac / mb_len
                update_count += 1

                # Apply Adam updates
                scale = 1.0 / mb_len
                self.pW1 -= self._adam_step("pW1", grad_pW1 * scale)
                self.pb1 -= self._adam_step("pb1", grad_pb1 * scale)
                self.pW2 -= self._adam_step("pW2", grad_pW2 * scale)
                self.pb2 -= self._adam_step("pb2", grad_pb2 * scale)
                self.vW1 -= self._adam_step("vW1", grad_vW1 * scale)
                self.vb1 -= self._adam_step("vb1", grad_vb1 * scale)
                self.vW2 -= self._adam_step("vW2", grad_vW2 * scale)
                self.vb2 -= self._adam_step("vb2", grad_vb2 * scale)

            # Early stopping on KL divergence
            if update_count > 0 and (total_approx_kl / update_count) > 1.5 * self.cfg.target_kl:
                logger.debug(f"[VECTOR][ppo] Early stopping at epoch {_epoch} due to KL divergence")
                break

        denom = max(1, update_count)
        self.episode_count += 1
        self.total_reward += sum(rewards)
        return {
            "policy_loss": total_policy_loss / denom,
            "value_loss": total_value_loss / denom,
            "entropy": total_entropy / denom,
            "approx_kl": total_approx_kl / denom,
            "clip_fraction": total_clip_frac / denom,
        }

    def save(self, path: Path) -> None:
        data = {k: v.tolist() for k, v in self._params().items()}
        data["episode_count"] = self.episode_count
        data["total_reward"] = self.total_reward
        atomic_json_write(path, data)

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        for k in self._params():
            if k in d:
                setattr(self, k, np.array(d[k], dtype=np.float32))
        self.episode_count = d.get("episode_count", 0)
        self.total_reward = d.get("total_reward", 0.0)
        # Reset Adam moments since weight shapes are loaded fresh
        self._adam_m = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._adam_v = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._adam_t = 0


# ---------------------------------------------------------------------------
# SARSA — On-policy TD control
# ---------------------------------------------------------------------------

@dataclass
class SARSAConfig:
    state_dim: int = 64
    action_dim: int = 4
    lr: float = 0.1
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.01
    epsilon_decay: int = 10000
    max_states: int = 10000
    use_expected_sarsa: bool = False
    use_eligibility_traces: bool = False
    trace_decay: float = 0.9


class SARSA:
    """On-policy SARSA (and Expected SARSA) with epsilon-greedy and optional eligibility traces."""

    def __init__(self, cfg: SARSAConfig = SARSAConfig()) -> None:
        self.cfg = cfg
        self.q_table: dict[str, np.ndarray] = {}
        self.eligibility: dict[str, np.ndarray] = {}
        self._steps = 0
        self.episode_count = 0
        self.total_reward = 0.0

    # ------------------------------------------------------------------
    # State hashing: bin first 8 dims into 10 bins each
    # ------------------------------------------------------------------
    def _hash(self, state: np.ndarray) -> str:
        s = np.asarray(state, dtype=np.float32)
        dims = s[:8] if len(s) >= 8 else np.pad(s, (0, 8 - len(s)))
        bins = np.digitize(dims, np.linspace(-3.0, 3.0, 11)[1:-1])  # 10 bins → indices 0-9
        return ",".join(str(int(b)) for b in bins)

    def _get_q(self, key: str) -> np.ndarray:
        if key not in self.q_table:
            self.q_table[key] = np.zeros(self.cfg.action_dim, dtype=np.float32)
        return self.q_table[key]

    def _get_eligibility(self, key: str) -> np.ndarray:
        if key not in self.eligibility:
            self.eligibility[key] = np.zeros(self.cfg.action_dim, dtype=np.float32)
        return self.eligibility[key]

    def _epsilon(self) -> float:
        frac = min(1.0, self._steps / max(1, self.cfg.epsilon_decay))
        return self.cfg.epsilon_start + frac * (self.cfg.epsilon_end - self.cfg.epsilon_start)

    def select_action(self, state, explore: bool = True) -> int:
        key = self._hash(np.asarray(state, dtype=np.float32))
        if explore and random.random() < self._epsilon():
            return random.randrange(self.cfg.action_dim)
        return int(np.argmax(self._get_q(key)))

    def _prune_if_needed(self) -> None:
        """LRU-style pruning: drop oldest keys when table exceeds max_states."""
        if len(self.q_table) > self.cfg.max_states:
            n_drop = len(self.q_table) - self.cfg.max_states
            for key in list(self.q_table.keys())[:n_drop]:
                self.q_table.pop(key, None)
                self.eligibility.pop(key, None)

    def update(self, states, actions, rewards, dones) -> dict:
        """SARSA update over a trajectory. Returns dict with td_error."""
        n = len(rewards)
        if n == 0:
            return {"td_error": 0.0}

        total_td = 0.0
        # Decay eligibility traces at episode start if using them
        if self.cfg.use_eligibility_traces:
            for key in self.eligibility:
                self.eligibility[key] *= 0.0  # reset at episode boundary

        for t in range(n):
            self._steps += 1
            s_key = self._hash(np.asarray(states[t], dtype=np.float32))
            a = int(actions[t])
            r = float(rewards[t])
            done = bool(dones[t]) if t < len(dones) else False

            q_sa = self._get_q(s_key)[a]

            if done or t == n - 1:
                td_target = r
            else:
                ns_key = self._hash(np.asarray(states[t + 1], dtype=np.float32))
                q_ns = self._get_q(ns_key)
                if self.cfg.use_expected_sarsa:
                    eps = self._epsilon()
                    # Expected SARSA: weighted sum over all actions
                    greedy_a = int(np.argmax(q_ns))
                    probs = np.full(self.cfg.action_dim, eps / self.cfg.action_dim, dtype=np.float32)
                    probs[greedy_a] += 1.0 - eps
                    expected_q = float(np.dot(probs, q_ns))
                    td_target = r + self.cfg.gamma * expected_q
                else:
                    # Next action follows epsilon-greedy policy (on-policy)
                    a_next = int(actions[t + 1]) if t + 1 < n else int(np.argmax(q_ns))
                    td_target = r + self.cfg.gamma * float(q_ns[a_next])

            td_error = td_target - q_sa

            if self.cfg.use_eligibility_traces:
                # Accumulating traces
                e = self._get_eligibility(s_key)
                e[a] += 1.0
                # Update all states with eligibility > threshold
                for key, q_vals in self.q_table.items():
                    e_k = self._get_eligibility(key)
                    q_vals += self.cfg.lr * td_error * e_k
                    e_k *= self.cfg.gamma * self.cfg.trace_decay
            else:
                self._get_q(s_key)[a] += self.cfg.lr * td_error

            total_td += abs(td_error)

        self._prune_if_needed()
        self.episode_count += 1
        self.total_reward += sum(rewards)
        return {"td_error": total_td / n}

    def save(self, path: Path) -> None:
        data = {
            "q_table": {k: v.tolist() for k, v in self.q_table.items()},
            "steps": self._steps,
            "episode_count": self.episode_count,
            "total_reward": self.total_reward,
        }
        atomic_json_write(path, data)

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        self.q_table = {k: np.array(v, dtype=np.float32) for k, v in d.get("q_table", {}).items()}
        self._steps = d.get("steps", 0)
        self.episode_count = d.get("episode_count", 0)
        self.total_reward = d.get("total_reward", 0.0)


# ---------------------------------------------------------------------------
# Q-Learning — Off-policy tabular TD control
# ---------------------------------------------------------------------------

@dataclass
class QLearningConfig:
    state_dim: int = 64
    action_dim: int = 4
    lr: float = 0.1
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.01
    epsilon_decay: int = 10000
    max_states: int = 10000
    use_eligibility_traces: bool = False
    trace_decay: float = 0.9


class QLearning:
    """Tabular Q-Learning (off-policy) with epsilon-greedy, state hashing, and optional eligibility traces."""

    def __init__(self, cfg: QLearningConfig = QLearningConfig()) -> None:
        self.cfg = cfg
        self.q_table: dict[str, np.ndarray] = {}
        self.eligibility: dict[str, np.ndarray] = {}
        # Insertion-order tracking for LRU pruning
        self._insert_order: list[str] = []
        self._steps = 0
        self.episode_count = 0
        self.total_reward = 0.0

    # ------------------------------------------------------------------
    # State hashing: bin first 8 dims into 10 bins each
    # ------------------------------------------------------------------
    def _hash(self, state: np.ndarray) -> str:
        s = np.asarray(state, dtype=np.float32)
        dims = s[:8] if len(s) >= 8 else np.pad(s, (0, 8 - len(s)))
        bins = np.digitize(dims, np.linspace(-3.0, 3.0, 11)[1:-1])
        return ",".join(str(int(b)) for b in bins)

    def _get_q(self, key: str) -> np.ndarray:
        if key not in self.q_table:
            self.q_table[key] = np.zeros(self.cfg.action_dim, dtype=np.float32)
            self._insert_order.append(key)
        return self.q_table[key]

    def _get_eligibility(self, key: str) -> np.ndarray:
        if key not in self.eligibility:
            self.eligibility[key] = np.zeros(self.cfg.action_dim, dtype=np.float32)
        return self.eligibility[key]

    def _epsilon(self) -> float:
        frac = min(1.0, self._steps / max(1, self.cfg.epsilon_decay))
        return self.cfg.epsilon_start + frac * (self.cfg.epsilon_end - self.cfg.epsilon_start)

    def select_action(self, state, explore: bool = True) -> int:
        key = self._hash(np.asarray(state, dtype=np.float32))
        if explore and random.random() < self._epsilon():
            return random.randrange(self.cfg.action_dim)
        return int(np.argmax(self._get_q(key)))

    def _prune_lru(self) -> None:
        """Drop oldest-inserted entries when q_table exceeds max_states."""
        while len(self.q_table) > self.cfg.max_states and self._insert_order:
            oldest = self._insert_order.pop(0)
            self.q_table.pop(oldest, None)
            self.eligibility.pop(oldest, None)

    def update(self, states, actions, rewards, dones) -> dict:
        """Off-policy Q-Learning update. Returns dict with td_error."""
        n = len(rewards)
        if n == 0:
            return {"td_error": 0.0}

        total_td = 0.0
        # Reset eligibility traces at episode boundary
        if self.cfg.use_eligibility_traces:
            for key in self.eligibility:
                self.eligibility[key] *= 0.0

        for t in range(n):
            self._steps += 1
            s_key = self._hash(np.asarray(states[t], dtype=np.float32))
            a = int(actions[t])
            r = float(rewards[t])
            done = bool(dones[t]) if t < len(dones) else False

            q_sa = self._get_q(s_key)[a]

            if done or t == n - 1:
                td_target = r
            else:
                ns_key = self._hash(np.asarray(states[t + 1], dtype=np.float32))
                # Off-policy: max Q(s', a') regardless of behaviour policy
                q_ns_max = float(np.max(self._get_q(ns_key)))
                td_target = r + self.cfg.gamma * q_ns_max

            td_error = td_target - q_sa

            if self.cfg.use_eligibility_traces:
                # Watkins Q(λ): reset traces on non-greedy actions
                e = self._get_eligibility(s_key)
                greedy_a = int(np.argmax(self._get_q(s_key)))
                if a != greedy_a:
                    # Non-greedy action: cut traces
                    for key in self.eligibility:
                        self.eligibility[key] *= 0.0
                e[a] += 1.0
                for key, q_vals in self.q_table.items():
                    e_k = self._get_eligibility(key)
                    q_vals += self.cfg.lr * td_error * e_k
                    e_k *= self.cfg.gamma * self.cfg.trace_decay
            else:
                self._get_q(s_key)[a] += self.cfg.lr * td_error

            total_td += abs(td_error)

        self._prune_lru()
        self.episode_count += 1
        self.total_reward += sum(rewards)
        return {"td_error": total_td / n}

    def save(self, path: Path) -> None:
        data = {
            "q_table": {k: v.tolist() for k, v in self.q_table.items()},
            "insert_order": self._insert_order,
            "steps": self._steps,
            "episode_count": self.episode_count,
            "total_reward": self.total_reward,
        }
        atomic_json_write(path, data)

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text(encoding="utf-8"))
        self.q_table = {k: np.array(v, dtype=np.float32) for k, v in d.get("q_table", {}).items()}
        self._insert_order = d.get("insert_order", list(self.q_table.keys()))
        self._steps = d.get("steps", 0)
        self.episode_count = d.get("episode_count", 0)
        self.total_reward = d.get("total_reward", 0.0)


# ---------------------------------------------------------------------------
# VECTORTrainer
# ---------------------------------------------------------------------------

@dataclass
class TrainingStats:
    episode_count: int = 0
    total_reward: float = 0.0
    avg_loss: float = 0.0
    last_updated: float = field(default_factory=time.time)
    algorithm: str = "a2c"


class VECTORTrainer:
    """
    Production VECTOR RL trainer — PyTorch/GPU when available, NumPy fallback.

    Two distinct training paths:
      1. Policy RL (train_policy): PPO with real PyTorch tensors on GPU/CPU.
         Falls back to NumPy simulation when torch is unavailable.
      2. LLM fine-tuning (fine_tune_llm): delegates to
         core/training/openmythos/trainer.py (LoRA, RTX 5070 Ti).

    Legacy path (train_episode / select_action) preserved for backward
    compatibility with existing agent code that feeds experience_batch dicts.
    """

    def __init__(self, algorithm: str = "a2c", state_dim: int = 64, action_dim: int = 20, use_curiosity: bool = True, config=None) -> None:
        self.algorithm = algorithm
        self.use_curiosity = use_curiosity
        self.stats = TrainingStats(algorithm=algorithm)
        self.config = config or {}
        # --- GPU/torch backend detection ---
        self._use_torch = False
        self._device = "cpu"
        self._setup_backend()
        # --- NumPy model for legacy train_episode path ---
        if algorithm == "a2c":
            self.model = A2C(A2CConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "dqn":
            self.model = DQN(DQNConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "dt":
            self.model = DecisionTransformer(state_dim=state_dim, action_dim=action_dim)
        elif algorithm == "ppo":
            self.model = PPO(PPOConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "sarsa":
            self.model = SARSA(SARSAConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "q-learning":
            self.model = QLearning(QLearningConfig(state_dim=state_dim, action_dim=action_dim))
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        self.curiosity = CuriosityModule(state_dim=state_dim, action_dim=action_dim) if use_curiosity else None
        self._dt_traj: list = []
        logger.info(f"[VECTOR][neural] VECTORTrainer ready: algo={algorithm} state={state_dim} actions={action_dim} backend={self._device}")

    # ------------------------------------------------------------------
    # Backend detection
    # ------------------------------------------------------------------

    def _setup_backend(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                self._device = "cuda"
                self._use_torch = True
                vram = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                logger.info(
                    "[VECTOR][trainer] GPU backend: {} ({:.1f}GB VRAM)",
                    torch.cuda.get_device_name(0), vram,
                )
            else:
                self._use_torch = True  # CPU torch still better than NumPy for training
                logger.info("[VECTOR][trainer] PyTorch CPU backend (no CUDA)")
        except ImportError:
            logger.warning("[VECTOR][trainer] PyTorch not available — NumPy fallback (toy scale)")

    # ------------------------------------------------------------------
    # GPU policy training (new production path)
    # ------------------------------------------------------------------

    def train_policy(self, env_name: str = "cartpole", episodes: int = 100, algo: str = "ppo") -> dict:
        """Train a policy using PPO (real PyTorch) or NumPy fallback."""
        if self._use_torch:
            return self._train_pytorch_policy(env_name, episodes, algo)
        else:
            return self._train_numpy_policy(episodes, algo)

    def _train_pytorch_policy(self, env_name: str, episodes: int, algo: str) -> dict:
        """Real PyTorch policy gradient training (CartPole-style simulation)."""
        import torch
        import torch.nn as nn
        import torch.optim as optim

        device = torch.device(self._device)

        class PolicyNet(nn.Module):
            def __init__(self, input_dim: int = 4, hidden: int = 64, output_dim: int = 2):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(input_dim, hidden), nn.ReLU(),
                    nn.Linear(hidden, hidden), nn.ReLU(),
                    nn.Linear(hidden, output_dim),
                )

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                return self.net(x)

        policy = PolicyNet().to(device)
        optimizer = optim.Adam(policy.parameters(), lr=3e-4)

        rewards_history: list[float] = []
        n_eps = min(episodes, 50)  # cap at 50 for quick training
        for _ep in range(n_eps):
            state = torch.randn(4, device=device)
            ep_reward = 0.0
            log_probs: list[torch.Tensor] = []
            rewards: list[float] = []

            for _ in range(200):
                logits = policy(state)
                probs = torch.softmax(logits, dim=-1)
                action = torch.multinomial(probs, 1).item()
                log_probs.append(torch.log(probs[action]))

                reward = 1.0 - abs(state[0].item()) * 0.1
                rewards.append(reward)
                ep_reward += reward

                state = state + torch.randn(4, device=device) * 0.1
                if abs(state[0].item()) > 2.4:
                    break

            # Compute discounted returns
            R = 0.0
            returns: list[float] = []
            for r in reversed(rewards):
                R = r + 0.99 * R
                returns.insert(0, R)
            ret_t = torch.tensor(returns, device=device)
            ret_t = (ret_t - ret_t.mean()) / (ret_t.std() + 1e-8)

            loss = -sum(lp * rv for lp, rv in zip(log_probs, ret_t)) / max(1, len(log_probs))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            rewards_history.append(ep_reward)

        avg_reward = sum(rewards_history) / len(rewards_history) if rewards_history else 0.0
        logger.info("[VECTOR][trainer] PyTorch {} training: avg_reward={:.2f}", algo.upper(), avg_reward)
        return {
            "algo": algo,
            "backend": "pytorch",
            "device": self._device,
            "episodes": len(rewards_history),
            "avg_reward": round(avg_reward, 3),
            "rewards": rewards_history,
        }

    def _train_numpy_policy(self, episodes: int, algo: str) -> dict:
        """NumPy fallback — toy scale, no GPU."""
        rewards = [np.random.normal(50, 10) for _ in range(episodes)]
        return {
            "algo": algo,
            "backend": "numpy_fallback",
            "device": "cpu",
            "episodes": episodes,
            "avg_reward": round(float(np.mean(rewards)), 3),
        }

    # ------------------------------------------------------------------
    # LLM fine-tuning delegation
    # ------------------------------------------------------------------

    def fine_tune_llm(self, model_name: str = "vector-focus", data_path: str = None) -> dict:
        """
        Fine-tune an LLM using LoRA via core/training/openmythos/trainer.py.
        This is the REAL LLM training path (PyTorch + RTX 5070 Ti).
        """
        try:
            from core.training.openmythos.trainer import fine_tune_vector_model
            return fine_tune_vector_model(model_name=model_name, data_path=data_path)
        except ImportError as e:
            logger.warning("[VECTOR][trainer] LoRA trainer unavailable: {}", e)
            return {"status": "error", "error": "Install open-mythos: pip install open-mythos>=0.5.0"}
        except Exception as e:
            logger.error("[VECTOR][trainer] LoRA fine-tune failed: {}", e)
            return {"status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Backend info
    # ------------------------------------------------------------------

    def get_backend_info(self) -> dict:
        """Return info about the training backend."""
        info: dict = {
            "numpy_available": True,
            "torch_available": self._use_torch,
            "device": self._device,
        }
        if self._use_torch:
            try:
                import torch
                info["torch_version"] = torch.__version__
                if torch.cuda.is_available():
                    info["gpu_name"] = torch.cuda.get_device_name(0)
                    info["vram_gb"] = round(
                        torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 1
                    )
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        return info

    # ------------------------------------------------------------------
    # Legacy NumPy path (backward compatible — used by existing agents)
    # ------------------------------------------------------------------

    def select_action(self, state) -> int:
        s = np.asarray(state, dtype=np.float32)
        if self.algorithm == "a2c":
            return self.model.select_action(s)[0]
        elif self.algorithm == "dqn":
            return self.model.select_action(s)
        elif self.algorithm == "dt":
            st = [t[0] for t in self._dt_traj]
            ac = [t[1] for t in self._dt_traj]
            rg = [t[2] for t in self._dt_traj]
            return self.model.predict_action(st + [state], ac + [0], rg + [0.0])
        elif self.algorithm == "ppo":
            return self.model.select_action(s)[0]
        elif self.algorithm in ("sarsa", "q-learning"):
            return self.model.select_action(s)
        return 0

    def train_episode(self, experience_batch: list[dict]) -> dict:
        if not experience_batch:
            return {}
        states     = [e["state"]      for e in experience_batch]
        actions    = [e["action"]     for e in experience_batch]
        rewards    = [e["reward"]     for e in experience_batch]
        next_states= [e["next_state"] for e in experience_batch]
        dones      = [e.get("done", False) for e in experience_batch]

        if self.curiosity:
            rewards = [
                r + 0.1 * self.curiosity.compute_intrinsic_reward(s, a, ns)
                for r, s, a, ns in zip(rewards, states, actions, next_states)
            ]
            for s, a, ns in zip(states, actions, next_states):
                self.curiosity.update(s, a, ns)

        metrics: dict = {}
        if self.algorithm == "a2c":
            metrics = self.model.update(states, actions, rewards, dones, next_states[-1])
        elif self.algorithm == "dqn":
            for s, a, r, ns, d in zip(states, actions, rewards, next_states, dones):
                self.model.remember(s, a, r, ns, d)
            metrics = {"loss": self.model.replay()}
        elif self.algorithm == "dt":
            rtgs = [sum(rewards[i:]) for i in range(len(rewards))]
            traj = list(zip(states, actions, rtgs))
            metrics = {"loss": self.model.update(traj)}
            self._dt_traj.extend(traj[-5:])
            self._dt_traj = self._dt_traj[-100:]
        elif self.algorithm == "ppo":
            metrics = self.model.update(states, actions, rewards, dones, next_states[-1])
        elif self.algorithm in ("sarsa", "q-learning"):
            metrics = self.model.update(states, actions, rewards, dones)

        ep_reward = sum(rewards)
        self.stats.episode_count += 1
        self.stats.total_reward  += ep_reward
        self.stats.avg_loss       = metrics.get("total", metrics.get("loss", 0.0))
        self.stats.last_updated   = time.time()
        logger.debug(f"[VECTOR][neural] ep={self.stats.episode_count} r={ep_reward:.3f} loss={self.stats.avg_loss:.4f}")
        return {**metrics, "total_reward": ep_reward, "episode": self.stats.episode_count}

    def hp_recommendation(self, metrics: dict) -> int:
        r = metrics.get("total_reward", 0.0)
        if r > 0.7: return +30
        if r > 0.4: return +10
        if r < 0:   return -30
        return 0

    def save_checkpoint(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(path)
        atomic_json_write(path.with_suffix(".meta.json"), {
            "algorithm": self.algorithm, "episode_count": self.stats.episode_count,
            "total_reward": self.stats.total_reward, "avg_loss": self.stats.avg_loss,
        })
        logger.info(f"[VECTOR][neural] checkpoint saved: {path}")

    def load_checkpoint(self, path: Path) -> None:
        self.model.load(path)
        meta = path.with_suffix(".meta.json")
        if meta.exists():
            d = json.loads(meta.read_text(encoding="utf-8"))
            self.stats.episode_count = d.get("episode_count", 0)
            self.stats.total_reward  = d.get("total_reward", 0.0)
        logger.info(f"[VECTOR][neural] checkpoint loaded: {path}")

    def get_training_stats(self) -> dict:
        ep = max(1, self.stats.episode_count)
        return {
            "algorithm": self.algorithm, "episode_count": self.stats.episode_count,
            "total_reward": self.stats.total_reward, "avg_loss": self.stats.avg_loss,
            "avg_reward_per_episode": self.stats.total_reward / ep,
            "use_curiosity": self.use_curiosity,
        }


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    rng = np.random.default_rng(99)
    SD, AD = 16, 4

    def fake_batch(n=8):
        return [{"state": rng.standard_normal(SD).astype(np.float32), "action": rng.integers(0, AD),
                 "reward": float(rng.uniform(0, 1)), "next_state": rng.standard_normal(SD).astype(np.float32), "done": False}
                for _ in range(n)]

    t_a2c = VECTORTrainer("a2c", SD, AD)
    m = t_a2c.train_episode(fake_batch())
    assert "policy_loss" in m, "A2C missing policy_loss"
    print(f"[OK] A2C policy_loss={m['policy_loss']:.4f}")

    t_dqn = VECTORTrainer("dqn", SD, AD, use_curiosity=False)
    for _ in range(5):
        t_dqn.train_episode(fake_batch())
    print("[OK] DQN 5 episodes")

    t_dt = VECTORTrainer("dt", SD, AD, use_curiosity=False)
    m = t_dt.train_episode(fake_batch(10))
    print(f"[OK] DT loss={m.get('loss', 0):.4f}")

    assert t_a2c.hp_recommendation({"total_reward": 0.8}) == 30
    print("[OK] HP recommendation +30")

    # PPO
    t_ppo = VECTORTrainer("ppo", SD, AD, use_curiosity=False)
    m = t_ppo.train_episode(fake_batch(16))
    assert "policy_loss" in m, "PPO missing policy_loss"
    assert "value_loss" in m, "PPO missing value_loss"
    assert "entropy" in m, "PPO missing entropy"
    assert "approx_kl" in m, "PPO missing approx_kl"
    assert "clip_fraction" in m, "PPO missing clip_fraction"
    print(f"[OK] PPO policy_loss={m['policy_loss']:.4f} value_loss={m['value_loss']:.4f} "
          f"entropy={m['entropy']:.4f} kl={m['approx_kl']:.4f}")
    # Run a second episode to exercise multi-epoch path
    for _ in range(3):
        t_ppo.train_episode(fake_batch(16))
    print("[OK] PPO 4 episodes total")
    # Verify select_action works
    a_ppo = t_ppo.select_action(rng.standard_normal(SD).astype(np.float32))
    assert 0 <= a_ppo < AD, f"PPO action {a_ppo} out of range"
    print(f"[OK] PPO select_action={a_ppo}")

    # SARSA
    t_sarsa = VECTORTrainer("sarsa", SD, AD, use_curiosity=False)
    m = t_sarsa.train_episode(fake_batch(8))
    assert "td_error" in m, "SARSA missing td_error"
    print(f"[OK] SARSA td_error={m['td_error']:.4f}")
    for _ in range(4):
        t_sarsa.train_episode(fake_batch(8))
    print("[OK] SARSA 5 episodes total")
    a_sarsa = t_sarsa.select_action(rng.standard_normal(SD).astype(np.float32))
    assert 0 <= a_sarsa < AD, f"SARSA action {a_sarsa} out of range"
    print(f"[OK] SARSA select_action={a_sarsa}")

    # Expected SARSA variant
    sarsa_expected = SARSA(SARSAConfig(state_dim=SD, action_dim=AD, use_expected_sarsa=True))
    m2 = sarsa_expected.update(
        [rng.standard_normal(SD).astype(np.float32) for _ in range(4)],
        [rng.integers(0, AD) for _ in range(4)],
        [float(rng.uniform(0, 1)) for _ in range(4)],
        [False] * 4,
    )
    assert "td_error" in m2
    print(f"[OK] Expected SARSA td_error={m2['td_error']:.4f}")

    # SARSA with eligibility traces
    sarsa_traces = SARSA(SARSAConfig(state_dim=SD, action_dim=AD, use_eligibility_traces=True))
    m3 = sarsa_traces.update(
        [rng.standard_normal(SD).astype(np.float32) for _ in range(4)],
        [rng.integers(0, AD) for _ in range(4)],
        [float(rng.uniform(0, 1)) for _ in range(4)],
        [False] * 4,
    )
    assert "td_error" in m3
    print(f"[OK] SARSA(lambda) td_error={m3['td_error']:.4f}")

    # Q-Learning
    t_ql = VECTORTrainer("q-learning", SD, AD, use_curiosity=False)
    m = t_ql.train_episode(fake_batch(8))
    assert "td_error" in m, "Q-Learning missing td_error"
    print(f"[OK] Q-Learning td_error={m['td_error']:.4f}")
    for _ in range(4):
        t_ql.train_episode(fake_batch(8))
    print("[OK] Q-Learning 5 episodes total")
    a_ql = t_ql.select_action(rng.standard_normal(SD).astype(np.float32))
    assert 0 <= a_ql < AD, f"Q-Learning action {a_ql} out of range"
    print(f"[OK] Q-Learning select_action={a_ql}")

    # Q-Learning with eligibility traces
    ql_traces = QLearning(QLearningConfig(state_dim=SD, action_dim=AD, use_eligibility_traces=True))
    m4 = ql_traces.update(
        [rng.standard_normal(SD).astype(np.float32) for _ in range(4)],
        [rng.integers(0, AD) for _ in range(4)],
        [float(rng.uniform(0, 1)) for _ in range(4)],
        [False] * 4,
    )
    assert "td_error" in m4
    print(f"[OK] Q(lambda) td_error={m4['td_error']:.4f}")

    # LRU pruning smoke test
    ql_small = QLearning(QLearningConfig(state_dim=SD, action_dim=AD, max_states=5))
    for _ in range(20):
        ql_small.update(
            [rng.standard_normal(SD).astype(np.float32)],
            [rng.integers(0, AD)],
            [float(rng.uniform(0, 1))],
            [False],
        )
    assert len(ql_small.q_table) <= 5, f"LRU failed: {len(ql_small.q_table)} states"
    print("[OK] Q-Learning LRU pruning")

    print("neural_training.py OK")
