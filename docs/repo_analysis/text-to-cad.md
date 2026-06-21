# text-to-cad — Absorption Analysis

**Verdict:** SKIP (out of mission; core not cleanly Python-portable as a runtime gain)

## What it is
- **Repo:** `earthtojake/text-to-cad` (brand: "CAD Skills"), MIT (`LICENSE:1` — `Copyright (c) 2026 earthtojake`).
- **What it does:** A *skills library* (Claude Code / Codex agent skills) for turning natural-language / image / 2D-drawing requests into parametric CAD geometry and adjacent hardware-design artifacts: STEP/STP (primary), STL/3MF/GLB (secondary), DXF (2D), URDF/SRDF/SDF (robot description), G-code (slicing), plus printer push (Bambu Labs) and parts sourcing (`step.parts`). See skill table `README.md:47-59`.
- **CAD engine:** **build123d** on top of **OpenCascade** via the `cadquery-ocp` (OCP) Python bindings — `packages/cadpy/pyproject.toml:9-13` (`dependencies = ["build123d", "cadquery-ocp"]`). Not OpenSCAD; not raw cadquery (uses build123d's higher-level API). README badges confirm build123d + OCP + OpenCascade (`README.md:25-26`).
- **Stack split:**
  - **Python:** `packages/cadpy/` (~15.7k LOC across `src/cadpy/*.py`) — STEP generation, GLB/topology export, STL/3MF export, assembly helpers, selector-ref syntax, validators, measurement/inspection. Plus `packages/cadpy_metadata` (dependency-free metadata helpers). Skill CLIs: `python scripts/step | inspect | snapshot` (`skills/cad/SKILL.md:47-51`). Extra Python deps: `ezdxf`, `trimesh`, `lxml`, `networkx`, `playwright` (`requirements-dev.txt`).
  - **JS/web (large):** `packages/cadjs` (Three.js render/runtime), `packages/implicitjs` (GLSL SDF raymarch), `viewer/` — a **React 18 + Vite + Three.js + Tailwind** browser app deployed to **Vercel** (`viewer/package.json`), plus a `moveit2_server` (ROS MoveIt2). The CAD Viewer (preview, snapshots, animation) is fundamentally a JS/web product.
- **Delivery model:** It is *agent skills + plugins*, not a service or library you `pip install` as a feature. Install paths are `npx skills install …`, `codex plugin add cad@…`, `claude plugin install cad@…` (`README.md:70-91`). The "intelligence" is the SKILL.md prompt-engineering; the engine underneath is just build123d.

## VECTOR already has
**Nothing CAD/3D — confirmed.**
- `*.py` grep for `cadquery|build123d|openscad|opencascade|stl|3mf|gcode|glb|slicer` returned **zero real CAD hits**. The 68 raw matches are all false positives: `STL` = statsmodels *Seasonal-Trend-Loess* decomposition in the finance district (`districts/investment/vector_finagent/Analytics/statsmodels_wrapper/timeseries_models.py:158-162`), `\bstep\b` = training-loop "step", `mesh` = the shadowbroker *network* mesh (`districts/intelligence/shadowbroker_server/services/mesh/*`).
- No CAD libs in any `requirements*.txt` (grep for `cadquery|build123d|trimesh|openscad|ezdxf` → NONE).
- 39 districts exist (`districts/`); none is CAD/hardware/fabrication. Closest adjacent is `districts/science/` (a generic `science_agent.py`) and `home_assistant/` — neither touches geometry.
- So this would be a genuinely **new capability**, not an upgrade.

## Mission fit
Honest take: **poor fit for this owner's JARVIS, today.** VECTOR's mission is an autonomous personal-assistant civilization for a KIIT CSE student/builder — memory, comms, coding, research, finance, content, learning. CAD/robotics is a real engineering domain but it is **out-of-mission niche**:
- No evidence the owner does mechanical CAD, 3D printing, or robotics in the brain vault goals (profile = software builder, RTX 5070 Ti used for LLM inference/training, not a print farm). The owner's hardware is a laptop GPU, not a CNC/printer rig.
- The value of this repo is overwhelmingly the **agent-skill prompt scaffolding + the JS viewer**, neither of which VECTOR needs: VECTOR already has its own skills/governor/districts architecture, and a built-in HUD frontend.
- Adopting it would mean owning **build123d + OCP** (heavy OpenCascade native deps) plus a React/Three.js/Vercel viewer just to serve a use case the owner hasn't asked for. That is exactly the "shiny-object" trap flagged in the owner profile.

## Python-portable core?
- **Python (portable in principle):** `cadpy` STEP/STL/3MF/GLB generation + build123d authoring + DXF (`ezdxf`) + URDF/SRDF/SDF emitters. These *are* Python and could be wrapped behind a VECTOR district.
- **But "absorb gaps only, reimplement in Python, no foreign traces" does not buy much here:** the actual engine (build123d/OCP) is a third-party pip dependency you'd just `pip install` — there's nothing novel to reimplement. `cadpy` itself is ~15.7k LOC of thin orchestration *around* build123d (selector refs, validators, assembly helpers, export plumbing). Reimplementing that to avoid copying = large effort for a niche, with no proprietary algorithm being captured.
- **JS/web (not portable):** the CAD Viewer (`viewer/`, React+Three.js), `cadjs`, `implicitjs` (GLSL SDF), and `moveit2_server` are the polished, demo-worthy half and are **inherently web/ROS** — they cannot be "reimplemented in Python" cheaply and VECTOR has no consumer for them.
- Net: the cleanly-absorbable Python slice is just "call build123d," which isn't an absorption — it's adding a dependency.

## Genuine gaps / value
- VECTOR genuinely has **zero** text→geometry capability (confirmed). If the owner ever pivots to hardware/robotics/3D-printing, this is the best-engineered OSS starting point: STEP-first, validated, build123d-based, MIT.
- The **SKILL.md workflow discipline** (classify → brief → plan → generate → geometric validate → snapshot → repair loop, `skills/cad/SKILL.md:59-72`) is a well-designed agent pattern worth *learning from* even outside CAD.
- The **`step.parts` off-the-shelf-component search** and **DXF/SendCutSend pre-flight checks** are tidy real-world fabrication touches.
- None of these rise to "needed now."

## Integration plan (only if owner explicitly wants CAD later)
- **Shape:** a new `districts/cad/` district (matches VECTOR's `districts/` model), not a core module — CAD is domain work, not infrastructure.
- **Engine:** `pip install build123d cadquery-ocp ezdxf trimesh` (use build123d directly; do NOT vendor `cadpy` — wrap the library).
- **Seams:** register a `CADAgent` in the agent registry; expose `generate_step(brief) / inspect / export_stl` as MCP tools in `core/mcp_server.py`; route via `core/city/governor.py` (96 routing defs already). A proactive trigger could attach to the orphaned `hands/` execution engine (`hands/runner.py`) if/when that engine is wired.
- **Viewer:** skip the React viewer entirely; if preview is needed, render GLB into the existing VECTOR HUD frontend or emit a snapshot PNG.
- **Effort:** ~1–2 days for a thin "text→STEP→STL + validate" district reusing build123d; weeks if URDF/robotics/viewer parity is wanted. Disproportionate to demonstrated need.

## Recommendation
**SKIP — do not absorb now (priority: LOW).** VECTOR confirmedly has no CAD capability, but that is by design: CAD/robotics/3D-printing is off-mission for this owner's software-builder JARVIS, and the repo's real value (the React/Three.js viewer + the agent-skill prompt scaffolding) is precisely the part VECTOR can't use and shouldn't reimplement. The genuinely portable slice reduces to "add build123d as a dependency," which is not an absorption and carries heavy OpenCascade native baggage for a use case nobody has requested. Bookmark this repo as the canonical starting point *if and when* the owner pivots to hardware — at that point stand up a lean `districts/cad/` that wraps build123d directly (no `cadpy`/viewer fork), register it through the governor + MCP, and reuse the SKILL.md validate→snapshot→repair loop as the workflow pattern. Until that pivot is explicit, absorbing this is textbook shiny-object scope creep.
