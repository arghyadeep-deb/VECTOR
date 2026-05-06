"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface SecurityEvent {
  id: string;
  event_type: string;
  content: string;
  timestamp: string;
  tags: string;
}

export default function SecurityPage() {
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/security/recent?limit=20`)
      .then((r) => r.json())
      .then((d) => setEvents(d.events ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#ff4444" }}>Security</h2>
      {loading && <p>Loading...</p>}
      {!loading && events.length === 0 && <p style={{ color: "#00ff88" }}>No security events. All clear.</p>}
      {events.map((e) => (
        <div key={e.id} style={{ borderLeft: "3px solid #ff4444", paddingLeft: "1rem", marginBottom: "0.8rem" }}>
          <div style={{ color: "#888", fontSize: "0.8em" }}>{e.timestamp?.slice(0, 19)}</div>
          <div style={{ color: "#ff8800", marginTop: "0.2rem" }}>[{e.event_type}]</div>
          <div>{e.content}</div>
        </div>
      ))}
    </main>
  );
}
