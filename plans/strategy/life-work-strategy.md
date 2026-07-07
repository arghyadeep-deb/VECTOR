# Life & Work Strategy — 6 Analyses
> 2026-07-07, Fable 5. Task P3.2 (strategy half). Grounded in owner profile
> (memory `user_arghyadeep_profile.md`, `brain/GOALS.md`) + observed multi-session
> behavior. Reflective sections marked [NEEDS OWNER INPUT] where a conversation
> would sharpen them. This is advisory, not prescriptive.

## Owner snapshot (the ground the analysis stands on)
Arghyadeep Deb, KIIT CSE 2023-27, RTX 5070 Ti. Ambition: build VECTOR (real
JARVIS) at the highest level + secure family's future. Strengths: fast
applied learner, cross-domain systems thinking, blends technical+business.
Weaknesses (self-identified): **over-commit + shiny-object syndrome.** Observed
pattern across sessions: **builds capability relentlessly, rarely operates it.**

---

## 5. The single binding constraint (do this one first — highest value)
**The binding constraint is NOT capability — it's OPERATION.** VECTOR is ~90%
built and has been for weeks, but it has never run as a service. Every session
asked "what more can I build," while the built system stayed powered off. Effort
is pouring into the non-constraint (more features) instead of the constraint
(shipping-to-running). **The one move that relieves it:** install VECTOR as a
service and run it for two weeks. Once it's running: the trust ladder starts
earning autonomy, real bugs surface (the true last 10%), and "VECTOR" becomes a
thing that does work instead of a thing that's built. Everything else — the
skills, the routing, the districts — only delivers value downstream of this.
Until then, more building is motion without progress.

## 6. The 30-day bus factor (what breaks if you vanish)
Load-bearing things that live only in the owner's head / are undocumented:
- **VECTOR isn't a service** — if the owner vanishes, VECTOR does nothing (it's
  only ever run manually). FIX: install the service (durable, survives absence).
- **Operational knowledge** (how to start Wan2GP/ComfyUI, record wake samples,
  the admin steps) — undocumented as runbooks until now. PARTIALLY FIXED: the
  new `vector-run-and-operate` + `vector-build-and-env` skills capture this.
- **Cloud credentials/accounts** (Cloudflare, Supabase, Turso, 13 LLM keys) —
  in .env, known only to owner. FIX: a sealed credential inventory + recovery doc
  (NOT in the public repo).
- **The "why" of decisions** — now largely captured in memory + the new
  `vector-*` skills + this handoff. Bus factor improved this session.
Plan: install the service (removes the biggest you-shaped hole), write a private
credentials-recovery doc, keep graduating tacit knowledge into skills.

## 4. Repeated decisions → standing policies (stop re-litigating)
Decisions the owner remakes from scratch (with the latent rule to codify):
| Recurring decision | Latent rule → standing policy |
|---|---|
| "What should I build next in VECTOR?" | POLICY: default to OPERATE/consolidate, not build. Only build if it unblocks running. (Reversible, low-stakes — autopilot toward operation.) |
| "Should I use paid or free for X?" | POLICY: free-tier-first, always. Paid only with explicit ROI. (Already the de-facto rule — make it standing.) |
| "Should Claude do this action?" | POLICY: reversible → yes; irreversible/outward → explicit approval. (The permission gateway already encodes this — trust it.) |
| "Is this feature good enough to ship?" | POLICY: passes the evidence gate (smoke/integration/quality-gate) → ship; else don't. Never judge by eye. |
Sorted by reversibility × stakes: the owner is SLOW on cheap reversible calls
(what to build — over-deliberated) and should autopilot those; and should stay
careful on the few expensive irreversible ones (deploy, spend, force-push).

---

## 1. Ikigai / single direction [NEEDS OWNER INPUT — draft]
Intersection of (love + skill + world-need + pay) given the profile:
- **Love + skill:** building autonomous AI systems that actually work; blending
  technical + business; systems thinking.
- **World-need + pay (2026):** autonomous agent systems, AI infra/tooling, and
  "AI that reliably does real work" are exactly where value is accruing.
- **Candidate single direction:** *become the person who ships reliable
  autonomous AI systems* — VECTOR is the proof-of-work/portfolio, not a
  scattered set of projects. Publish VECTOR's hardest solved problems (the
  multi-provider free-tier routing, the Darwinian agent economy, the local-first
  privacy model) as the public narrative. The "party explanation": *"I build AI
  that runs autonomously on free infrastructure — a personal JARVIS that's also
  a testbed for how autonomous agents should actually work."*
- Path options: (a) for yourself (VECTOR → open-source cred → consulting/product),
  (b) collaborators (a small autonomous-agents team), (c) corporate (AI infra/
  agent roles — VECTOR is an extraordinary interview artifact). Given the
  student stage + family-security goal, (c)-as-floor + (a)-as-upside is the
  pragmatic combo. [OWNER: which pulls you — independence or stability first?]

## 2. Steelman: your biggest bet is WRONG [NEEDS OWNER INPUT — adversarial draft]
The biggest bet = "build VECTOR to the highest level as the path to both
mastery and income." The steelman AGAINST it:
- **Load-bearing unchecked belief:** "a maximally-capable personal system proves
  my ability and creates value." But value comes from OPERATED, USEFUL systems
  seen by others — not from private capability. VECTOR is huge and unrun; the
  market can't see or use it. The bet may be optimizing *capability* when the
  world rewards *shipped, legible outcomes*.
- **Second unchecked belief:** "more features = more proof." The shiny-object
  pattern suggests the building is partly avoidance of the harder, scarier work
  of shipping/showing/selling. 1.5M LOC unrun is not obviously more impressive
  than a small thing that runs and helps people.
- **What would change your mind:** if you shipped ONE narrow VECTOR capability
  publicly (or to 5 users) and it created more opportunity than the last 6
  months of building — that's evidence the bet should flip from "build more" to
  "ship narrow." **Would you even notice?** Only if you define a success metric
  BEFORE (users/opportunity), not "did I build something cool" (always yes).

## 3. What AI makes obsolete vs 10× for you [NEEDS OWNER INPUT — draft]
- **About to go obsolete / stop investing:** hand-writing boilerplate, being a
  "coder who implements specs" (models do this now — see the Bitter Lesson doc),
  and breadth-for-breadth's-sake learning. VECTOR's own hand-coded routing tables
  are a microcosm — models will subsume them.
- **About to 10× / pour in:** *taste and judgment about what to build*, systems
  architecture, the ability to ORCHESTRATE agents (you're literally building
  this), and blending technical + business to spot/ship real value. The scarce
  skill in 2026 isn't writing code — it's deciding what should exist and making
  autonomous systems reliable. That's your edge; sharpen it.
- **This-year changes:** ship one narrow thing publicly; stop equating LOC with
  progress; invest in operating + distribution, not just building.

## Provenance
2026-07-07. Sources: memory `user_arghyadeep_profile.md`, `brain/GOALS.md`,
observed session behavior. The [NEEDS OWNER INPUT] sections are strong drafts
to react to in a conversation, not final answers. The analytical sections
(#5 binding constraint, #6 bus factor, #4 policies) are grounded and actionable now.
