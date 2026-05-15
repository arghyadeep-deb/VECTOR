"""VECTOR neural training — A2C, DQN, Curiosity, DecisionTransformer, VECTORTrainer."""
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
        path.write_text(json.dumps({k: getattr(self, k).tolist() for k in ["W1","b1","Wp","bp","Wv","bv"]}))

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text())
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
        path.write_text(json.dumps({k: getattr(self, k).tolist() for k in ["W1","b1","W2","b2"]}))

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text())
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
        path.write_text(json.dumps({k: getattr(self, k).tolist() for k in ["Ws","Wa","Wr","Wq","Wk","Wv","Wout","bout"]}))

    def load(self, path: Path) -> None:
        d = json.loads(path.read_text())
        for k in ["Ws","Wa","Wr","Wq","Wk","Wv","Wout","bout"]:
            if k in d:
                setattr(self, k, np.array(d[k], dtype=np.float32))


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
    Unified RL training orchestrator for VECTOR autonomous agents.

    Wires world-state vectors into A2C/DQN/DT action selection, feeds
    outcomes back through the policy layer, and recommends HP deltas.
    """

    def __init__(self, algorithm: str = "a2c", state_dim: int = 64, action_dim: int = 20, use_curiosity: bool = True) -> None:
        self.algorithm = algorithm
        self.use_curiosity = use_curiosity
        self.stats = TrainingStats(algorithm=algorithm)
        if algorithm == "a2c":
            self.model = A2C(A2CConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "dqn":
            self.model = DQN(DQNConfig(state_dim=state_dim, action_dim=action_dim))
        elif algorithm == "dt":
            self.model = DecisionTransformer(state_dim=state_dim, action_dim=action_dim)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        self.curiosity = CuriosityModule(state_dim=state_dim, action_dim=action_dim) if use_curiosity else None
        self._dt_traj: list = []
        logger.info(f"[VECTOR][neural] VECTORTrainer ready: algo={algorithm} state={state_dim} actions={action_dim}")

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
        path.with_suffix(".meta.json").write_text(json.dumps({
            "algorithm": self.algorithm, "episode_count": self.stats.episode_count,
            "total_reward": self.stats.total_reward, "avg_loss": self.stats.avg_loss,
        }))
        logger.info(f"[VECTOR][neural] checkpoint saved: {path}")

    def load_checkpoint(self, path: Path) -> None:
        self.model.load(path)
        meta = path.with_suffix(".meta.json")
        if meta.exists():
            d = json.loads(meta.read_text())
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
    print("neural_training.py OK")
