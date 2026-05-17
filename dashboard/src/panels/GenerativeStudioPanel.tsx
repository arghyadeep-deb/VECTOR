/**
 * VECTOR Generative Studio Panel
 * Image, Video, Lip Sync, and Animate tabs for manual AI media generation.
 * Connects to: studio_server /api/media/* endpoints
 * Backend priority: Wan2GP (free local) → sd.cpp (offline) → Muapi.ai (cloud)
 */
import { useState, useEffect, useCallback } from "react";

const API = "http://127.0.0.1:51200";

type Tab = "image" | "video" | "lipsync" | "animate";

interface GenerationResult {
  id: string;
  action: string;
  prompt: string;
  url: string;
  backend: string;
  model: string;
  created_at: string;
  media_type: "image" | "video";
}

interface BackendStatus {
  muapi: { configured: boolean; balance: number };
  wan2gp: { configured: boolean; connected: boolean; matched_models: number };
  local: { binary_available: boolean; models: { id: string; name: string; downloaded: boolean }[] };
}

interface MediaModel {
  id: string;
  name: string;
  category: string;
}

// ── Shared helpers ──────────────────────────────────────────────────────────

const ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"];

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, color: "#9ca3af" }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: ok ? "#10b981" : "#4b5563", display: "inline-block" }} />
      {label}
    </span>
  );
}

function ResultPreview({ result }: { result: GenerationResult }) {
  return (
    <div style={{ background: "#111827", borderRadius: 8, overflow: "hidden", border: "1px solid #1f2937" }}>
      {result.media_type === "image" ? (
        <img src={result.url} alt={result.prompt} style={{ width: "100%", maxHeight: 260, objectFit: "contain" }} />
      ) : (
        <video src={result.url} controls style={{ width: "100%", maxHeight: 260 }} />
      )}
      <div style={{ padding: "8px 12px", fontSize: 11, color: "#6b7280" }}>
        <span style={{ color: "#d1d5db" }}>{result.model}</span> · {result.backend} · {new Date(result.created_at).toLocaleTimeString()}
        <a href={result.url} download style={{ marginLeft: 8, color: "#6366f1" }}>↓ download</a>
      </div>
    </div>
  );
}

// ── Individual tabs ─────────────────────────────────────────────────────────

function ImageTab({ models, onGenerate, generating }: {
  models: MediaModel[];
  onGenerate: (action: string, params: Record<string, string>) => void;
  generating: boolean;
}) {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("flux-dev");
  const [ar, setAr] = useState("1:1");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <textarea
        value={prompt}
        onChange={e => setPrompt(e.target.value)}
        placeholder="Describe the image…"
        rows={3}
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: 8, resize: "vertical", fontFamily: "inherit", fontSize: 13 }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <select value={model} onChange={e => setModel(e.target.value)}
          style={{ flex: 2, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select value={ar} onChange={e => setAr(e.target.value)}
          style={{ flex: 1, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {ASPECT_RATIOS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <button
        disabled={generating || !prompt.trim()}
        onClick={() => onGenerate("generate_image", { prompt, model, aspect_ratio: ar })}
        style={{ background: generating ? "#374151" : "#4f46e5", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: generating ? "not-allowed" : "pointer", fontSize: 13 }}
      >
        {generating ? "Generating…" : "Generate Image"}
      </button>
    </div>
  );
}

function VideoTab({ models, onGenerate, generating }: {
  models: MediaModel[];
  onGenerate: (action: string, params: Record<string, string>) => void;
  generating: boolean;
}) {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("kling-v3");
  const [ar, setAr] = useState("16:9");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <textarea
        value={prompt}
        onChange={e => setPrompt(e.target.value)}
        placeholder="Describe the video…"
        rows={3}
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: 8, resize: "vertical", fontFamily: "inherit", fontSize: 13 }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <select value={model} onChange={e => setModel(e.target.value)}
          style={{ flex: 2, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select value={ar} onChange={e => setAr(e.target.value)}
          style={{ flex: 1, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {ASPECT_RATIOS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <button
        disabled={generating || !prompt.trim()}
        onClick={() => onGenerate("generate_video", { prompt, model, aspect_ratio: ar })}
        style={{ background: generating ? "#374151" : "#7c3aed", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: generating ? "not-allowed" : "pointer", fontSize: 13 }}
      >
        {generating ? "Generating… (may take minutes)" : "Generate Video"}
      </button>
    </div>
  );
}

function LipSyncTab({ models, onGenerate, generating }: {
  models: MediaModel[];
  onGenerate: (action: string, params: Record<string, string>) => void;
  generating: boolean;
}) {
  const [portrait, setPortrait] = useState("");
  const [audio, setAudio] = useState("");
  const [model, setModel] = useState("infinite-talk");
  const [isVideo, setIsVideo] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 11, color: "#6b7280", margin: 0 }}>
        Feed a portrait photo (or video) + an audio narration → talking head video with lip sync.
      </p>
      <input value={portrait} onChange={e => setPortrait(e.target.value)} placeholder="Portrait image URL (or local path)"
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }} />
      <input value={audio} onChange={e => setAudio(e.target.value)} placeholder="Audio file URL (or local path to .wav)"
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }} />
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select value={model} onChange={e => setModel(e.target.value)}
          style={{ flex: 2, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <label style={{ fontSize: 12, color: "#9ca3af", display: "flex", alignItems: "center", gap: 4 }}>
          <input type="checkbox" checked={isVideo} onChange={e => setIsVideo(e.target.checked)} />
          Portrait is video
        </label>
      </div>
      <button
        disabled={generating || !portrait.trim() || !audio.trim()}
        onClick={() => onGenerate("lipsync", { portrait, audio, model, is_video: isVideo ? "true" : "false" })}
        style={{ background: generating ? "#374151" : "#0f766e", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: generating ? "not-allowed" : "pointer", fontSize: 13 }}
      >
        {generating ? "Generating… (may take minutes)" : "Generate Lip Sync"}
      </button>
    </div>
  );
}

function AnimateTab({ models, onGenerate, generating }: {
  models: MediaModel[];
  onGenerate: (action: string, params: Record<string, string>) => void;
  generating: boolean;
}) {
  const [image, setImage] = useState("");
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("kling-i2v");
  const [ar, setAr] = useState("16:9");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 11, color: "#6b7280", margin: 0 }}>Animate a still image into a video clip.</p>
      <input value={image} onChange={e => setImage(e.target.value)} placeholder="Image URL (or local path)"
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }} />
      <input value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Motion prompt (optional)"
        style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }} />
      <div style={{ display: "flex", gap: 8 }}>
        <select value={model} onChange={e => setModel(e.target.value)}
          style={{ flex: 2, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select value={ar} onChange={e => setAr(e.target.value)}
          style={{ flex: 1, background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "6px 8px", fontSize: 12 }}>
          {ASPECT_RATIOS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <button
        disabled={generating || !image.trim()}
        onClick={() => onGenerate("animate_image", { image, prompt, model, aspect_ratio: ar })}
        style={{ background: generating ? "#374151" : "#b45309", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: generating ? "not-allowed" : "pointer", fontSize: 13 }}
      >
        {generating ? "Animating…" : "Animate Image"}
      </button>
    </div>
  );
}

// ── Main panel ──────────────────────────────────────────────────────────────

export default function GenerativeStudioPanel() {
  const [tab, setTab] = useState<Tab>("image");
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [models, setModels] = useState<Record<string, MediaModel[]>>({});
  const [generating, setGenerating] = useState(false);
  const [lastResult, setLastResult] = useState<GenerationResult | null>(null);
  const [history, setHistory] = useState<GenerationResult[]>([]);
  const [error, setError] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/media/status`);
      if (r.ok) setStatus(await r.json());
    } catch {}
  }, []);

  const fetchModels = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/media/models`);
      if (r.ok) setModels(await r.json());
    } catch {}
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/media/history`);
      if (r.ok) setHistory(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchModels();
    fetchHistory();
    const t = setInterval(() => { fetchStatus(); fetchHistory(); }, 10000);
    return () => clearInterval(t);
  }, [fetchStatus, fetchModels, fetchHistory]);

  const handleGenerate = async (action: string, params: Record<string, string>) => {
    setGenerating(true);
    setError("");
    setLastResult(null);
    try {
      const r = await fetch(`${API}/api/media/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...params }),
      });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
      const result: GenerationResult = {
        id: data.id || String(Date.now()),
        action,
        prompt: params.prompt || "",
        url: data.url || data.image_path || "",
        backend: data.backend || "unknown",
        model: params.model || "",
        created_at: new Date().toISOString(),
        media_type: ["generate_image", "generate_i2i", "background_remove", "upscale"].includes(action) ? "image" : "video",
      };
      setLastResult(result);
      setHistory(prev => [result, ...prev.slice(0, 19)]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const TAB_MODELS: Record<Tab, string> = {
    image: "t2i",
    video: "t2v",
    lipsync: "lipsync",
    animate: "i2v",
  };
  const currentModels = models[TAB_MODELS[tab]] || [];

  const TAB_COLORS: Record<Tab, string> = {
    image: "#4f46e5", video: "#7c3aed", lipsync: "#0f766e", animate: "#b45309",
  };

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif", color: "#f9fafb", height: "100%", overflowY: "auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "#e5e7eb" }}>Generative Studio</h3>
        {status && (
          <div style={{ display: "flex", gap: 10 }}>
            <StatusDot ok={status.muapi.configured} label={`Muapi ${status.muapi.configured ? `$${status.muapi.balance.toFixed(2)}` : "off"}`} />
            <StatusDot ok={status.wan2gp.connected} label={`Wan2GP ${status.wan2gp.connected ? `${status.wan2gp.matched_models}m` : "off"}`} />
            <StatusDot ok={status.local.binary_available} label="sd.cpp" />
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 14 }}>
        {(["image", "video", "lipsync", "animate"] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              background: tab === t ? TAB_COLORS[t] : "#1f2937",
              color: tab === t ? "#fff" : "#9ca3af",
              border: "none", borderRadius: 6, padding: "5px 12px", cursor: "pointer", fontSize: 12, fontWeight: tab === t ? 600 : 400,
            }}>
            {t === "image" ? "Image" : t === "video" ? "Video" : t === "lipsync" ? "Lip Sync" : "Animate"}
          </button>
        ))}
      </div>

      {/* Active tab */}
      <div style={{ marginBottom: 14 }}>
        {tab === "image" && <ImageTab models={currentModels} onGenerate={handleGenerate} generating={generating} />}
        {tab === "video" && <VideoTab models={currentModels} onGenerate={handleGenerate} generating={generating} />}
        {tab === "lipsync" && <LipSyncTab models={currentModels} onGenerate={handleGenerate} generating={generating} />}
        {tab === "animate" && <AnimateTab models={currentModels} onGenerate={handleGenerate} generating={generating} />}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: "#450a0a", border: "1px solid #b91c1c", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#fca5a5", marginBottom: 10 }}>
          {error}
        </div>
      )}

      {/* Latest result */}
      {lastResult && lastResult.url && (
        <div style={{ marginBottom: 14 }}>
          <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 6px" }}>Latest result</p>
          <ResultPreview result={lastResult} />
        </div>
      )}

      {/* History grid */}
      {history.length > 0 && (
        <div>
          <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 8px" }}>History ({history.length})</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
            {history.map(r => r.url && (
              <div key={r.id} style={{ background: "#111827", borderRadius: 6, overflow: "hidden", border: "1px solid #1f2937", cursor: "pointer" }}
                onClick={() => setLastResult(r)}>
                {r.media_type === "image"
                  ? <img src={r.url} alt="" style={{ width: "100%", height: 100, objectFit: "cover" }} />
                  : <div style={{ width: "100%", height: 100, background: "#1f2937", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24 }}>▶</div>
                }
                <p style={{ fontSize: 10, color: "#6b7280", margin: "4px 6px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.model}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
