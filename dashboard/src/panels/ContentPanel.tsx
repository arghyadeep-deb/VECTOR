/**
 * VECTOR Content Panel — Video pipeline monitor + trigger
 * Shows: queue, upload history, platform status, quick trigger
 * Connects to: studio_server /api/content/* endpoints
 */
import { useState, useEffect, useCallback } from "react";

const API = "http://127.0.0.1:51200";

interface ContentJob {
  id: string;
  topic: string;
  niche: string;
  platform: string;
  status: string;
  stage_pct: number;
  created_at: string;
  updated_at: string;
  youtube_url: string | null;
  instagram_url: string | null;
  video_path: string | null;
  error: string | null;
  upload_after: string | null;
}

interface PlatformStatus {
  youtube: boolean;
  instagram: boolean;
  elevenlabs: boolean;
  niche: string;
  upload_delay_min: number;
}

const STATUS_COLOR: Record<string, string> = {
  pending:    "#6b7280",
  scripting:  "#f59e0b",
  narrating:  "#f59e0b",
  rendering:  "#3b82f6",
  captioning: "#3b82f6",
  uploading:  "#8b5cf6",
  done:       "#10b981",
  cancelled:  "#6b7280",
  error:      "#ef4444",
};

const STATUS_LABEL: Record<string, string> = {
  pending:    "Pending",
  scripting:  "Writing script…",
  narrating:  "Generating voice…",
  rendering:  "Rendering MP4…",
  captioning: "Adding captions…",
  uploading:  "Uploading…",
  done:       "Published",
  cancelled:  "Cancelled",
  error:      "Error",
};

function fmt_time(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function ProgressBar({ pct, status }: { pct: number; status: string }) {
  const color = STATUS_COLOR[status] || "#00D4FF";
  return (
    <div style={{ height: 4, background: "rgba(255,255,255,0.08)", borderRadius: 4, marginTop: 6 }}>
      <div
        style={{
          height: "100%", width: `${pct}%`, background: color,
          borderRadius: 4, transition: "width 0.5s ease",
        }}
      />
    </div>
  );
}

function JobCard({ job, onCancel }: { job: ContentJob; onCancel: (id: string) => void }) {
  const color = STATUS_COLOR[job.status] || "#6b7280";
  const inProgress = ["pending","scripting","narrating","rendering","captioning","uploading"].includes(job.status);

  return (
    <div style={{
      background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: "12px 14px",
      marginBottom: 8, border: `1px solid rgba(255,255,255,0.07)`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: "#e5e5e5", marginBottom: 2,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {job.topic}
          </div>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {job.niche} · {job.platform} · {fmt_time(job.created_at)}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 12 }}>
          <span style={{
            fontSize: 11, padding: "2px 8px", borderRadius: 12,
            background: `${color}22`, color, border: `1px solid ${color}44`,
          }}>
            {STATUS_LABEL[job.status] || job.status}
          </span>
          {job.status === "uploading" && (
            <button
              onClick={() => onCancel(job.id)}
              style={{
                fontSize: 11, padding: "2px 8px", borderRadius: 6, cursor: "pointer",
                background: "rgba(239,68,68,0.15)", color: "#ef4444",
                border: "1px solid rgba(239,68,68,0.3)",
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {inProgress && <ProgressBar pct={job.stage_pct} status={job.status} />}

      {(job.youtube_url || job.instagram_url) && (
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          {job.youtube_url && (
            <a href={job.youtube_url} target="_blank" rel="noreferrer" style={{
              fontSize: 12, color: "#f00", textDecoration: "none",
              padding: "2px 8px", borderRadius: 6, background: "rgba(255,0,0,0.1)",
              border: "1px solid rgba(255,0,0,0.25)",
            }}>▶ YouTube</a>
          )}
          {job.instagram_url && (
            <a href={job.instagram_url} target="_blank" rel="noreferrer" style={{
              fontSize: 12, color: "#e1306c", textDecoration: "none",
              padding: "2px 8px", borderRadius: 6, background: "rgba(225,48,108,0.1)",
              border: "1px solid rgba(225,48,108,0.25)",
            }}>📸 Instagram</a>
          )}
        </div>
      )}

      {job.error && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#ef4444",
                      background: "rgba(239,68,68,0.08)", padding: "4px 8px", borderRadius: 4 }}>
          {job.error.slice(0, 120)}
        </div>
      )}
    </div>
  );
}

export function ContentPanel() {
  const [queue, setQueue]       = useState<ContentJob[]>([]);
  const [history, setHistory]   = useState<ContentJob[]>([]);
  const [status, setStatus]     = useState<PlatformStatus | null>(null);
  const [topic, setTopic]       = useState("");
  const [niche, setNiche]       = useState("AI");
  const [platform, setPlatform] = useState("both");
  const [triggering, setTriggering] = useState(false);
  const [tab, setTab]           = useState<"queue"|"history">("queue");

  const refresh = useCallback(async () => {
    try {
      const [qRes, hRes, sRes] = await Promise.all([
        fetch(`${API}/api/content/queue`).then(r => r.json()).catch(() => ({ jobs: [] })),
        fetch(`${API}/api/content/history`).then(r => r.json()).catch(() => ({ jobs: [] })),
        fetch(`${API}/api/content/status`).then(r => r.json()).catch(() => null),
      ]);
      setQueue(qRes.jobs || []);
      setHistory(hRes.jobs || []);
      setStatus(sRes);
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleGenerate = async () => {
    if (triggering) return;
    setTriggering(true);
    try {
      await fetch(`${API}/api/content/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: topic.trim() || null, platform, niche }),
      });
      setTopic("");
      setTimeout(refresh, 500);
    } catch {}
    setTriggering(false);
  };

  const handleCancel = async (jobId: string) => {
    try {
      await fetch(`${API}/api/content/cancel/${jobId}`, { method: "DELETE" });
      setTimeout(refresh, 300);
    } catch {}
  };

  const activeJobs  = queue.filter(j => !["done","cancelled","error"].includes(j.status));
  const displayJobs = tab === "queue" ? activeJobs : history;

  return (
    <div style={{
      background: "#0d1117", border: "1px solid rgba(0,212,255,0.12)",
      borderRadius: 12, padding: "16px", height: "100%",
      display: "flex", flexDirection: "column", gap: 12,
      fontFamily: "'Inter', sans-serif",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#00D4FF", letterSpacing: "0.06em" }}>
            CONTENT PIPELINE
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
            {activeJobs.length} active · {history.length} completed
          </div>
        </div>
        {/* Platform status dots */}
        {status && (
          <div style={{ display: "flex", gap: 6 }}>
            <span title={`YouTube ${status.youtube ? "connected" : "no credentials"}`}
              style={{ fontSize: 11, padding: "2px 8px", borderRadius: 12,
                       background: status.youtube ? "rgba(255,0,0,0.15)" : "rgba(107,114,128,0.2)",
                       color: status.youtube ? "#f00" : "#6b7280",
                       border: `1px solid ${status.youtube ? "rgba(255,0,0,0.3)" : "rgba(107,114,128,0.3)"}` }}>
              ▶ YT
            </span>
            <span title={`Instagram ${status.instagram ? "connected" : "no credentials"}`}
              style={{ fontSize: 11, padding: "2px 8px", borderRadius: 12,
                       background: status.instagram ? "rgba(225,48,108,0.15)" : "rgba(107,114,128,0.2)",
                       color: status.instagram ? "#e1306c" : "#6b7280",
                       border: `1px solid ${status.instagram ? "rgba(225,48,108,0.3)" : "rgba(107,114,128,0.3)"}` }}>
              📸 IG
            </span>
          </div>
        )}
      </div>

      {/* Quick trigger */}
      <div style={{ background: "rgba(0,212,255,0.05)", borderRadius: 8, padding: 12,
                    border: "1px solid rgba(0,212,255,0.1)" }}>
        <input
          value={topic}
          onChange={e => setTopic(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleGenerate()}
          placeholder="Video topic (or leave blank for auto)"
          style={{
            width: "100%", background: "transparent", border: "none",
            color: "#e5e5e5", fontSize: 13, outline: "none",
            marginBottom: 10, padding: "4px 0",
          }}
        />
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={niche} onChange={e => setNiche(e.target.value)}
            style={{ background: "#1a1a2e", color: "#a0a0a0", border: "1px solid rgba(255,255,255,0.1)",
                     borderRadius: 6, padding: "4px 8px", fontSize: 12, cursor: "pointer" }}>
            {["AI","finance","tech","health"].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <select value={platform} onChange={e => setPlatform(e.target.value)}
            style={{ background: "#1a1a2e", color: "#a0a0a0", border: "1px solid rgba(255,255,255,0.1)",
                     borderRadius: 6, padding: "4px 8px", fontSize: 12, cursor: "pointer" }}>
            {[["both","YT + IG"],["youtube","YouTube only"],["instagram","Instagram only"]].map(([v,l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <button
            onClick={handleGenerate}
            disabled={triggering}
            style={{
              marginLeft: "auto", background: triggering ? "rgba(0,212,255,0.2)" : "#00D4FF",
              color: triggering ? "#6b7280" : "#020A14",
              border: "none", borderRadius: 6, padding: "6px 16px",
              fontSize: 12, fontWeight: 600, cursor: triggering ? "not-allowed" : "pointer",
              transition: "all 0.2s",
            }}
          >
            {triggering ? "Starting…" : "Generate"}
          </button>
        </div>
        {status && (
          <div style={{ fontSize: 11, color: "#4a4a6a", marginTop: 8 }}>
            Nightly auto-generation at 22:00 · {status.upload_delay_min}min safety window
          </div>
        )}
      </div>

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: 4 }}>
        {(["queue","history"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, background: tab === t ? "rgba(0,212,255,0.12)" : "transparent",
            color: tab === t ? "#00D4FF" : "#6b7280",
            border: `1px solid ${tab === t ? "rgba(0,212,255,0.3)" : "rgba(255,255,255,0.06)"}`,
            borderRadius: 6, padding: "5px 0", fontSize: 12,
            cursor: "pointer", textTransform: "capitalize",
          }}>
            {t === "queue" ? `Queue (${activeJobs.length})` : `History (${history.length})`}
          </button>
        ))}
      </div>

      {/* Job list */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {displayJobs.length === 0 ? (
          <div style={{
            textAlign: "center", color: "#3a3a5a", fontSize: 13,
            paddingTop: 32,
          }}>
            {tab === "queue" ? "No active jobs — trigger one above" : "No completed videos yet"}
          </div>
        ) : (
          displayJobs.map(job => (
            <JobCard key={job.id} job={job} onCancel={handleCancel} />
          ))
        )}
      </div>
    </div>
  );
}
