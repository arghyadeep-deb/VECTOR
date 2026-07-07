---
name: power-moves
description: Load when the owner wants to run one of the 7 "Fable 5 Power Moves" — build an internal tool, audit past work, design a business, lead-gen+CRM, stock analysis, AI-automation consulting offer, or a multi-workstream research agent. Ready-to-run workflows wired to VECTOR's machinery. Triggers: "power move", "build me a tool", "audit my work", "design a business", "lead gen", "analyze this filing", "consulting offer", "research agent".
---

# Power Moves (Fable 5 Vol.2) — executed inside VECTOR

Seven high-leverage workflows. Each is grounded in real VECTOR machinery so it
runs on the owner's own system with free-tier LLM routing. Data source for all:
VECTOR Brain (`brain/`) + memory + past sessions. Authored 2026-07-07.

## When NOT to use this skill
For the underlying LLM routing use `vector-inference-routing`; for VECTOR's
districts use `vector-architecture-contract`.

## 1. Build an internal tool (kill your biggest weekly time-drain)
INPUT: the owner's repetitive weekly tasks. OUTPUT: one-file tool + plain
instructions. RUN: identify the biggest drain from the task list, then generate
a single-file tool (Python/HTML) into `tools/` or `districts/personal_growth/`.
Prompt: "Here are my repetitive weekly tasks: [X]. Identify the biggest time
drain, then build a simple ONE-FILE tool that replaces it, with plain-English
instructions." Wire it as a VECTOR skill if it recurs.

## 2. Audit past work (what worked / what you dropped)
Data: `brain/03 Reviews/`, memory files, git history. OUTPUT: ranked 10
improvements by effort×impact + a plan for the top 3. RUN via a research-district
task or directly. Prompt: "Search my last [N] months (brain vault + git). List
what worked, what I abandoned, where value is sitting. Rank 10 improvements by
effort vs impact; plan the top 3." (See `plans/strategy/` for a started version.)

## 3. Design a business (launch in 6 days)
Data: `brain/GOALS.md`, owner profile. OUTPUT: offer + customer + price + tools +
day-by-day plan. Prompt: "Review what you know about me (goals/skills/interests).
Context: [X]. Design ONE business I could launch in six days: the offer, the
customer, the price, the tools, a day-by-day plan." Push back on the first idea.
(Ties to `plans/strategy/life-work-strategy.md` #1 Ikigai.)

## 4. Lead generator + CRM (scrape → score → email → CRM)
VECTOR machinery: `core/scraper/` (prospect scrape), `provider_client` (score +
draft), comms channels (send), a CRM sink. OUTPUT: working pipeline. RUN: build
into `districts/agency/`. Prompt: "Build a lead-gen system that scrapes prospects
matching [criteria], scores by [factors], drafts a cold email each, logs to
[CRM]. Full working code + setup." SAFETY: sending emails is RED-tier
(permission gateway) — draft-and-queue, owner approves sends.

## 5. Stock / filing deep-analysis
VECTOR machinery: `districts/investment/` (stock_analyst, fundamentals_bot —
now on `domain:finance.analysis` chain), yfinance/akshare data. ANALYSIS ONLY
(never trades — see `plans/audits/trading-research-audit.md`). Prompt: "Analyze
this earnings report/filing: [X]. Ranked investment thesis, top red flags, what
a skeptical analyst would push back on." Runs through the investment district.

## 6. AI-automation consulting offer (lead-qualification agent)
OUTPUT: a $3-8k-deliverable build plan + working code for a client's
lead-qualification agent. VECTOR machinery: `districts/agency/` +
swarm/orchestrator + permission gateway (for the routing/escalation). Prompt:
"Design a lead-qualification agent for a client in [industry]: intake → score
against [criteria] → route qualified to [destination]. Build plan + working code."

## 7. Multi-workstream knowledge-base agent (orchestrator + parallel subagents)
VECTOR machinery: `core/swarm/orchestrator.py` (one orchestrator), cheap-subagent
routing via `provider_client` (a strong model orchestrates; cheaper free models
research branches in parallel), then synthesis. OUTPUT: one sourced report.
Prompt: "Break [research goal] into parallel workstreams. Assign each to a
subagent, define what each returns, then synthesize into one report with
sourcing." This is the highest-leverage move — it's literally what VECTOR's
swarm layer is for; route branches to different free providers to parallelize
for free (see `vector-inference-routing` domain chains).

## Cross-cutting: run these ON free infrastructure
All 7 route through `provider_client` (cloud-primary free tiers). The
multi-workstream one (#7) especially benefits from spreading branches across the
13 free providers so a "full analyst team" runs at $0. Sensitive data stays
local (sensitivity gate).

## Provenance and maintenance
2026-07-07. Each move is a workflow, not yet a built tool — running one produces
the artifact. Wire recurring ones into districts/skills. Ties to
`core/scraper/`, `districts/investment/`, `districts/agency/`, `core/swarm/`.
