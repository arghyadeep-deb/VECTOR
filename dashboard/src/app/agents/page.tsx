"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface Agent {
  agent_id: string;
  name: string;
  district: string;
  generation: number;
  health_points: number;
  is_alive: boolean;
}

function hpColor(hp: number) {
  if (hp > 700) return "#00ff88";
  if (hp > 400) return "#ffcc00";
  return "#ff4444";
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/agents`)
      .then((r) => r.json())
      .then((d) => setAgents(d.agents ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#00ff88" }}>Agents</h2>
      {loading && <p>Loading...</p>}
      {!loading && agents.length === 0 && <p style={{ color: "#888" }}>No agents registered.</p>}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ color: "#888", textAlign: "left" }}>
            <th>Name</th><th>District</th><th>Gen</th><th>HP</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.agent_id} style={{ borderTop: "1px solid #222" }}>
              <td>{a.name}</td>
              <td>{a.district}</td>
              <td>{a.generation}</td>
              <td style={{ color: hpColor(a.health_points) }}>{a.health_points}</td>
              <td style={{ color: a.is_alive ? "#00ff88" : "#ff4444" }}>{a.is_alive ? "alive" : "dead"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
