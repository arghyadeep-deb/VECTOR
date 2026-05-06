"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface Event {
  id: string;
  event_type: string;
  content: string;
  timestamp: string;
  source: string;
  tags: string;
}

export default function MemoryPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/memory/recent?limit=20`)
      .then((r) => r.json())
      .then((d) => setEvents(d.events ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <a href="/" style={{ color: "#888" }}>← home</a>
      <h2 style={{ color: "#00ff88" }}>Episodic Memory</h2>
      {loading && <p>Loading...</p>}
      {events.map((e) => (
        <div key={e.id} style={{ borderBottom: "1px solid #222", padding: "0.5rem 0" }}>
          <span style={{ color: "#00aaff" }}>[{e.event_type}]</span>{" "}
          <span style={{ color: "#888", fontSize: "0.8em" }}>{e.timestamp?.slice(0, 19)}</span>
          <div style={{ marginTop: "0.2rem" }}>{e.content}</div>
          {e.tags && <div style={{ color: "#555", fontSize: "0.8em" }}>{e.tags}</div>}
        </div>
      ))}
    </main>
  );
}
