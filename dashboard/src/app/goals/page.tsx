"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

export default function GoalsPage() {
  const [actions, setActions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/goals`)
      .then((r) => r.json())
      .then((d) => setActions(d.immediate_actions ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#00ff88" }}>Goals & Immediate Actions</h2>
      {loading && <p>Loading...</p>}
      {!loading && actions.length === 0 && <p style={{ color: "#888" }}>No immediate actions.</p>}
      <ul style={{ paddingLeft: "1.2rem" }}>
        {actions.map((a, i) => (
          <li key={i} style={{ padding: "0.4rem 0", borderBottom: "1px solid #1a1a1a" }}>{a}</li>
        ))}
      </ul>
    </main>
  );
}
