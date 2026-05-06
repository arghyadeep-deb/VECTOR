"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface Session {
  id: string;
  event_type: string;
  content: string;
  timestamp: string;
}

export default function CouncilPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/council/history?limit=10`)
      .then((r) => r.json())
      .then((d) => setSessions(d.sessions ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#00ff88" }}>LLM Council — Session History</h2>
      {loading && <p>Loading...</p>}
      {!loading && sessions.length === 0 && <p style={{ color: "#888" }}>No council sessions yet.</p>}
      {sessions.map((s) => (
        <div key={s.id} style={{ border: "1px solid #222", padding: "0.8rem", marginBottom: "0.8rem", borderRadius: "4px" }}>
          <div style={{ color: "#888", fontSize: "0.8em" }}>{s.timestamp?.slice(0, 19)}</div>
          <div style={{ marginTop: "0.3rem" }}>{s.content}</div>
        </div>
      ))}
    </main>
  );
}
