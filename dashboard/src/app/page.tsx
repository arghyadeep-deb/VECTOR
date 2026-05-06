"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_VECTOR_API ?? "https://vector-brain.fly.dev";

interface Status {
  status: string;
  version: string;
  environment: string;
  uptime_sec: number;
  last_heartbeat: string | null;
}

export default function Home() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    fetch(`${API}/status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setError("Brain server unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", background: "#0a0a0a", color: "#e0e0e0", minHeight: "100vh" }}>
      <h1 style={{ color: "#00ff88" }}>V.E.C.T.O.R</h1>
      <p style={{ color: "#888" }}>Virtual Entity for Cognitive Tasks &amp; Operational Reasoning</p>

      {error && <p style={{ color: "#ff4444" }}>{error}</p>}
      {status && (
        <div style={{ marginTop: "1rem", border: "1px solid #333", padding: "1rem", borderRadius: "4px" }}>
          <div>Status: <span style={{ color: status.status === "online" ? "#00ff88" : "#ff4444" }}>{status.status}</span></div>
          <div>Version: {status.version}</div>
          <div>Environment: {status.environment}</div>
          <div>Uptime: {Math.round(status.uptime_sec)}s</div>
          <div>Last heartbeat: {status.last_heartbeat ?? "—"}</div>
        </div>
      )}

      <nav style={{ marginTop: "2rem" }}>
        {["/agents", "/memory", "/goals", "/council", "/security", "/city"].map((p) => (
          <a key={p} href={p} style={{ color: "#00aaff", marginRight: "1.5rem" }}>{p}</a>
        ))}
      </nav>
    </main>
  );
}
