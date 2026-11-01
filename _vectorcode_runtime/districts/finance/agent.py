"""FinanceSwarm — orchestrates finance district (5 .md + 7 .py agents)."""

from __future__ import annotations

import sys, asyncio, importlib
from pathlib import Path; from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.city.prompt_agent import PromptAgent
from core.city.agent_registry import get_registry
from core.config import CONFIG
DISTRICT = Path(__file__).parent.name

TASK_ROLE_MAP: dict[str, set[str]] = {
    "expense": {"expense", "tracker", "spend"},
    "budget": {"budget", "analyst"},
    "tax": {"tax", "strategist", "calendar"},
    "upi": {"upi", "parser", "payment"},
    "fpa": {"fpa", "financial", "planning"},
    "llm_cost": {"llm", "cost", "tracker"},
    "financial": {"financial", "analyst"},
    "investment": {"investment", "researcher"},
    "bookkeeper": {"bookkeeper", "controller"},
    "default": {"finance", "financial"},
}

MD_FILES = ["finance-bookkeeper-controller", "finance-financial-analyst", "finance-fpa-analyst", "finance-investment-researcher", "finance-tax-strategist"]
PYTHON_AGENTS: list[tuple[str, str]] = [
    ("expense_tracker", "ExpenseTracker"), ("budget_analyst", "BudgetAnalyst"),
    ("tax_calendar", "TaxCalendar"), ("upi_parser", "UPIParser"),
    ("fpa_analyst", "FPAAnalyst"), ("llm_cost_tracker", "LLMCostTracker"),
    ("financial_analyst", "FinancialAnalyst"),
]

class FinanceSwarm(AgentBase):
    def __init__(self):
        super().__init__(agent_id="finance-swarm-001", name="FinanceSwarm", district=DISTRICT)
        self.health_points = 800
        self._agents: dict[str, AgentBase] = {}; self._agent_roles: dict[str, str] = {}
        self._load_agents()
    def _load_agents(self):
        r = get_registry()
        for stem in MD_FILES:
            aid = f"finance_{stem}_swarm_001"
            if r.get(aid): self._agents[aid] = r.get(aid); self._agent_roles[aid] = stem; continue
            fp = Path(__file__).parent / f"{stem}.md"
            if not fp.exists(): continue
            try:
                C = type(stem.replace("-","").title(), (PromptAgent,), {"__init__": lambda s, _p=str(fp), _i=aid, _d=DISTRICT: PromptAgent.__init__(s, _p, _i, _d)})
                a = C(); r.register(a); self._agents[aid] = a; self._agent_roles[aid] = stem
            except Exception as e: logger.warning("[FinanceSwarm] .md {}: {}", stem, e)
        for mod_name, cls_name in PYTHON_AGENTS:
            aid = f"finance_{mod_name}_swarm_001"
            if r.get(aid): self._agents[aid] = r.get(aid); self._agent_roles[aid] = mod_name; continue
            try:
                m = importlib.import_module(f"districts.finance.{mod_name}")
                c = getattr(m, cls_name); a = c(); r.register(a); self._agents[aid] = a; self._agent_roles[aid] = mod_name
            except Exception as e: logger.warning("[FinanceSwarm] py {}: {}", cls_name, e)
        logger.info("[FinanceSwarm] {} agents loaded", len(self._agents))
    def _score(self, aid, tt):
        r = self._agent_roles.get(aid,""); kw = TASK_ROLE_MAP.get(tt,TASK_ROLE_MAP["default"])
        return min(sum(1 for k in kw if k in r.lower())/max(len(kw),1)*2, 1)
    def _select(self, tt):
        if not self._agents: return None
        s = sorted([(a,self._score(a,tt)) for a in self._agents], key=lambda x:x[1], reverse=True)
        return self._agents[s[0][0]] if s[0][1]>0 else None
    async def dispatch(self, tt: str, p: dict) -> dict:
        a = self._select(tt)
        if a:
            try:
                if isinstance(a, PromptAgent): return await a.run({"query": p.get("query",p.get("prompt","")), "context": p.get("context",""), "timeout": p.get("timeout",60)})
                # 2026-09-24 (independent review finding -- HIGH, same class
                # found in CodingSwarm): tt (the real, Governor-authorized
                # task_type) must always win over anything the caller put
                # in p, never the reverse.
                return await a.run({**p, "type": tt})
            except Exception as e: logger.warning("[FinanceSwarm] fail {}: {}", a.name, e)
        return await self._fallback(tt, p)
    async def _fallback(self, tt, p):
        from core.inference.vectorcode_llm import chat
        q = p.get("query",p.get("prompt",f"Finance: {tt}")); ctx = p.get("context","")
        m = [{"role":"system","content":f"FinanceSwarm. No specialist for '{tt}'."}]
        if ctx: m.append({"role":"user","content":f"[Context]\n{ctx}"})
        m.append({"role":"user","content":q})
        try: return {"status":"ok","response":await chat(model=CONFIG.get("models",{}).get("reasoning","vector-reasoning"), messages=m, timeout=60),"agent":self.name,"fallback":True}
        except Exception as e: return {"status":"error","error":str(e),"agent":self.name}
    async def run(self, t: dict) -> dict:
        # 2026-07-30 audit fix: governor.dispatch() calls agent.run(task)
        # with the real user text nested at task["params"]["query"] (or
        # ["content"]), not at task["query"] — passing `t` itself as `p`
        # left the nested query invisible to dispatch()'s p.get("query", ...)
        # read, so every PromptAgent sub-agent got an empty query (live-
        # caught: "It seems like you haven't provided a query"). Same fix
        # already applied to coding/agent.py (CodingSwarm) on 2026-07-29;
        # flattening the real query onto params here too.
        task_type = t.get("type", t.get("task_type", "default"))
        real_query = (
            (t.get("params") or {}).get("query")
            or (t.get("params") or {}).get("content")
            or t.get("query")
            or t.get("prompt")
            or ""
        )
        params = dict(t.get("params") or {})
        params.setdefault("query", real_query)
        for k, v in t.items():
            if k not in ("type", "task_type", "params"):
                params.setdefault(k, v)
        return await self.dispatch(task_type, params)

if __name__=="__main__":
    async def _s():
        import sys as _s; _s.stdout.reconfigure(encoding="utf-8")
        s=FinanceSwarm()
        for tt in ["expense","budget","tax","investment","fpa"]:
            a=s._select(tt); print(f"  {tt:20s} → {a.name if a else 'NONE'}")
        print(f"Loaded {len(s._agents)} agents"); print("FinanceSwarm OK")
    asyncio.run(_s())
