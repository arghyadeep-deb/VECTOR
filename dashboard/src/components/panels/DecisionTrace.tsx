import { useEffect, useState } from "react";

export interface DecisionEvent {
  id?: string;
  action_type?: string;
  decision?: "GREEN" | "YELLOW" | "RED";
  score?: number;
  reasoning?: string;
  timestamp?: string;
}

const tierClass = (decision?: string) => {
  if (decision === "GREEN") return "tier tier-green";
  if (decision === "YELLOW") return "tier tier-yellow";
  if (decision === "RED") return "tier tier-red";
  return "tier";
};

export function DecisionTrace({ decisions = [] }: { decisions?: DecisionEvent[] }) {
  const [chains, setChains] = useState<any[]>([]);

  const loadReasoning = async (decision: DecisionEvent) => {
    const res = await fetch("/brain/reasoning/chains?limit=20");
    const data = await res.json();
    setChains(data.chains || []);
    return decision;
  };

  useEffect(() => {
    void loadReasoning({});
  }, []);

  return (
    <section className="panel decision-trace">
      <h2>Decision Trace</h2>
      <div className="decision-list">
        {decisions.map((decision, index) => (
          <button
            key={decision.id || `${decision.action_type}-${index}`}
            className={tierClass(decision.decision)}
            onClick={() => void loadReasoning(decision)}
          >
            <span>{decision.action_type || "decision"}</span>
            <strong>{decision.decision || "GREEN"}</strong>
          </button>
        ))}
      </div>
      <div className="reasoning-chain">
        {chains.slice(0, 20).map((chain, index) => (
          <article key={chain.chain_id || index}>
            <strong>{chain.action_taken}</strong>
            <p>{Array.isArray(chain.steps) ? chain.steps.join(" -> ") : chain.reasoning}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
