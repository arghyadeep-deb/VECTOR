<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/karpathy-micrograd.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: karpathy-micrograd
description: Step-by-step implementation guide for karpathy/micrograd — use during 2AM Karpathy sessions to build backprop intuition from scratch before touching PyTorch internals
---

# micrograd — Implementation Guide

## Purpose
Implement a scalar-valued autograd engine in ~150 lines of Python. micrograd gives bone-deep understanding of how backpropagation works before you use PyTorch's autograd as a black box. Essential prerequisite before studying nanoGPT.

## Key Files to Study (in order)
1. `micrograd/engine.py` — the `Value` class (~80 lines). This IS the autograd engine.
2. `micrograd/nn.py` — `Neuron`, `Layer`, `MLP` built on top of `Value`
3. `demo.ipynb` — trace a 2-layer MLP forward + backward pass by hand

## Implementation Steps
1. Implement `Value.__init__`: store `data`, `grad=0.0`, `_backward=lambda: None`, `_prev=set(children)`
2. Implement `Value.__add__`: create output `Value`, define `_backward` that accumulates `grad` to both inputs
3. Implement `Value.__mul__`: same pattern — `self.grad += other.data * out.grad` and vice versa
4. Implement `Value.tanh` or `Value.relu`: chain rule for the activation
5. Implement `Value.backward`: topological sort over `_prev` graph, call each `_backward` in reverse
6. Build `Neuron` on top: `w·x + b` followed by `tanh`. Then `Layer` and `MLP`.
7. Train on a toy dataset: MSE loss → `.backward()` → manual SGD update on all `.parameters()`

## Key Concepts
- **Chain rule**: every `_backward` function is just the local gradient × upstream gradient
- **Topological sort**: nodes must get their upstream gradient before their `_backward` fires — this is why you need the ordering
- **`+=` for gradients**: one `Value` can feed into multiple places — gradients accumulate (sum), not overwrite
- **`_prev` set**: tracks the graph structure. Without it, backward can't traverse the computation graph.

## VECTOR Application
Study micrograd before any Phase 3 LLM work. The mental model of "every operation has a local gradient, backward is just chain rule through the graph" is what lets you debug PyTorch training when gradients vanish or explode. After implementing micrograd, the transition to PyTorch's `autograd` feels trivial. This is a 2-hour session, not a multi-day project — implement it once, understand it completely.
