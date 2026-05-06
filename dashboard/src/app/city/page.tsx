"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface AgentData {
  name: string;
  district: string;
  health_points: number;
  generation: number;
  is_alive: boolean;
}

function hpBar(hp: number) {
  const pct = Math.min(100, (hp / 1000) * 100);
  const color = hp > 700 ? "#00ff88" : hp > 400 ? "#ffcc00" : "#ff4444";
  return (
    <div style={{ background: "#1a1a1a", height: "6px", width: "100%", borderRadius: "3px" }}>
      <div style={{ width: `${pct}%`, background: color, height: "6px", borderRadius: "3px" }} />
    </div>
  );
}

export default function CityPage() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/agents`)
      .then((r) => r.json())
      .then((d) => setAgents(d.agents ?? []))
      .finally(() => setLoading(false));
  }, []);

  const byDistrict = agents.reduce<Record<string, AgentData[]>>((acc, a) => {
    (acc[a.district] ??= []).push(a);
    return acc;
  }, {});

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#00ff88" }}>VECTOR City</h2>
      <p style={{ color: "#888" }}>
        {agents.filter((a) => a.is_alive).length} alive / {agents.length} total
      </p>
      {loading && <p>Loading...</p>}
      {Object.entries(byDistrict).map(([district, distAgents]) => (
        <div key={district} style={{ marginBottom: "1.5rem" }}>
          <h3 style={{ color: "#00aaff", marginBottom: "0.5rem" }}>#{district}</h3>
          {distAgents.map((a) => (
            <div key={a.name} style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "0.4rem" }}>
              <span style={{ width: "160px" }}>{a.name}</span>
              <span style={{ width: "40px", color: "#888" }}>g{a.generation}</span>
              <div style={{ flex: 1 }}>{hpBar(a.health_points)}</div>
              <span style={{ width: "50px", textAlign: "right" }}>{a.health_points}</span>
            </div>
          ))}
        </div>
      ))}
    </main>
  );
}
