/**
 * VECTOR Workflow Panel — Visual AI generation pipeline builder
 * Drag-and-drop node graph for building multi-step media workflows.
 * Supports both manual (owner-driven) and agent-executed pipelines.
 *
 * Connects to: studio_server /api/workflows/* endpoints
 * Node types: Image Gen, Video Gen, Lip Sync, Text Input, Output
 *
 * NOTE: Uses @xyflow/react for the graph canvas. Install via:
 *   npm install @xyflow/react
 */
import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://127.0.0.1:51200";

// ── Types ────────────────────────────────────────────────────────────────────

interface WorkflowNode {
  id: string;
  type: "image_gen" | "video_gen" | "lipsync" | "text_input" | "output";
  label: string;
  x: number;
  y: number;
  params: Record<string, string>;
}

interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

interface Workflow {
  id: string;
  name: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at: string;
  updated_at: string;
}

interface NodeRunResult {
  node_id: string;
  status: "pending" | "running" | "done" | "error";
  url?: string;
  error?: string;
}

// ── Node type configs ────────────────────────────────────────────────────────

const NODE_TYPES = {
  text_input: { label: "Text Input", color: "#374151", icon: "📝" },
  image_gen:  { label: "Image Gen",  color: "#4f46e5", icon: "🖼️" },
  video_gen:  { label: "Video Gen",  color: "#7c3aed", icon: "🎬" },
  lipsync:    { label: "Lip Sync",   color: "#0f766e", icon: "🎙️" },
  output:     { label: "Output",     color: "#065f46", icon: "📤" },
} as const;

// ── Simple canvas-based node graph (no external dependency) ──────────────────

function NodeCard({ node, selected, onSelect, onParamChange }: {
  node: WorkflowNode;
  selected: boolean;
  onSelect: () => void;
  onParamChange: (key: string, val: string) => void;
}) {
  const cfg = NODE_TYPES[node.type];
  return (
    <div
      onClick={onSelect}
      style={{
        position: "absolute", left: node.x, top: node.y,
        width: 180, background: "#111827",
        border: `2px solid ${selected ? cfg.color : "#374151"}`,
        borderRadius: 8, padding: "10px 12px",
        cursor: "pointer", userSelect: "none",
        boxShadow: selected ? `0 0 0 2px ${cfg.color}40` : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span>{cfg.icon}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#e5e7eb" }}>{node.label}</span>
      </div>
      {node.type === "text_input" && (
        <textarea
          value={node.params.text || ""}
          onChange={e => onParamChange("text", e.target.value)}
          placeholder="Enter text…"
          rows={2}
          onClick={e => e.stopPropagation()}
          style={{ width: "100%", background: "#1f2937", border: "1px solid #374151", borderRadius: 4, color: "#f9fafb", fontSize: 11, padding: 4, resize: "none", fontFamily: "inherit", boxSizing: "border-box" }}
        />
      )}
      {node.type === "image_gen" && (
        <input
          value={node.params.model || "flux-dev"}
          onChange={e => onParamChange("model", e.target.value)}
          placeholder="Model ID"
          onClick={e => e.stopPropagation()}
          style={{ width: "100%", background: "#1f2937", border: "1px solid #374151", borderRadius: 4, color: "#f9fafb", fontSize: 11, padding: 4, boxSizing: "border-box" }}
        />
      )}
      {node.type === "video_gen" && (
        <input
          value={node.params.model || "kling-v3"}
          onChange={e => onParamChange("model", e.target.value)}
          placeholder="Model ID"
          onClick={e => e.stopPropagation()}
          style={{ width: "100%", background: "#1f2937", border: "1px solid #374151", borderRadius: 4, color: "#f9fafb", fontSize: 11, padding: 4, boxSizing: "border-box" }}
        />
      )}
      {node.type === "lipsync" && (
        <>
          <input
            value={node.params.portrait || ""}
            onChange={e => onParamChange("portrait", e.target.value)}
            placeholder="Portrait URL"
            onClick={e => e.stopPropagation()}
            style={{ width: "100%", background: "#1f2937", border: "1px solid #374151", borderRadius: 4, color: "#f9fafb", fontSize: 11, padding: 4, marginBottom: 4, boxSizing: "border-box" }}
          />
          <input
            value={node.params.model || "infinite-talk"}
            onChange={e => onParamChange("model", e.target.value)}
            placeholder="Model ID"
            onClick={e => e.stopPropagation()}
            style={{ width: "100%", background: "#1f2937", border: "1px solid #374151", borderRadius: 4, color: "#f9fafb", fontSize: 11, padding: 4, boxSizing: "border-box" }}
          />
        </>
      )}
    </div>
  );
}

function WorkflowCanvas({ nodes, edges, selectedId, onSelectNode, onParamChange, runResults }: {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  selectedId: string | null;
  onSelectNode: (id: string) => void;
  onParamChange: (nodeId: string, key: string, val: string) => void;
  runResults: Record<string, NodeRunResult>;
}) {
  return (
    <div style={{ position: "relative", width: "100%", minHeight: 400, background: "#0f172a", borderRadius: 8, border: "1px solid #1f2937", overflow: "auto" }}>
      {/* Grid background */}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
        <defs>
          <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#1f2937" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        {/* Edges as lines */}
        {edges.map(edge => {
          const src = nodes.find(n => n.id === edge.source);
          const tgt = nodes.find(n => n.id === edge.target);
          if (!src || !tgt) return null;
          return (
            <line key={edge.id}
              x1={src.x + 90} y1={src.y + 50}
              x2={tgt.x + 90} y2={tgt.y + 10}
              stroke="#4f46e5" strokeWidth={1.5} strokeDasharray="4,2"
            />
          );
        })}
      </svg>
      {/* Nodes */}
      {nodes.map(node => (
        <div key={node.id}>
          <NodeCard
            node={node}
            selected={selectedId === node.id}
            onSelect={() => onSelectNode(node.id)}
            onParamChange={(k, v) => onParamChange(node.id, k, v)}
          />
          {/* Run result badge */}
          {runResults[node.id] && (
            <div style={{
              position: "absolute", left: node.x + 185, top: node.y,
              fontSize: 10, padding: "2px 6px", borderRadius: 4,
              background: runResults[node.id].status === "done" ? "#064e3b" : runResults[node.id].status === "error" ? "#450a0a" : "#1e3a5f",
              color: runResults[node.id].status === "done" ? "#6ee7b7" : runResults[node.id].status === "error" ? "#fca5a5" : "#93c5fd",
              whiteSpace: "nowrap",
            }}>
              {runResults[node.id].status === "done" ? "✓ done" : runResults[node.id].status === "error" ? "✗ error" : "⟳"}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Palette ──────────────────────────────────────────────────────────────────

function NodePalette({ onAdd }: { onAdd: (type: WorkflowNode["type"]) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, width: 120, flexShrink: 0 }}>
      <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 4px" }}>Add node</p>
      {(Object.entries(NODE_TYPES) as [WorkflowNode["type"], typeof NODE_TYPES[keyof typeof NODE_TYPES]][]).map(([type, cfg]) => (
        <button key={type} onClick={() => onAdd(type)}
          style={{ background: "#1f2937", border: `1px solid ${cfg.color}60`, borderRadius: 6, color: "#e5e7eb", padding: "6px 8px", cursor: "pointer", fontSize: 11, textAlign: "left", display: "flex", alignItems: "center", gap: 5 }}>
          {cfg.icon} {cfg.label}
        </button>
      ))}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

export default function WorkflowPanel() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [current, setCurrent] = useState<Workflow | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runResults, setRunResults] = useState<Record<string, NodeRunResult>>({});
  const [savingName, setSavingName] = useState("");
  const [error, setError] = useState("");
  const nodeCounter = useRef(0);

  const fetchWorkflows = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/workflows`);
      if (r.ok) setWorkflows(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  const newWorkflow = () => {
    setCurrent({ id: "", name: "Untitled", nodes: [], edges: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    setRunResults({});
    setSelectedNodeId(null);
    setSavingName("Untitled");
  };

  const loadWorkflow = async (id: string) => {
    try {
      const r = await fetch(`${API}/api/workflows/${id}`);
      if (r.ok) {
        const wf = await r.json();
        setCurrent(wf);
        setSavingName(wf.name);
        setRunResults({});
        setSelectedNodeId(null);
      }
    } catch {}
  };

  const saveWorkflow = async () => {
    if (!current) return;
    const wf = { ...current, name: savingName || current.name };
    try {
      let r;
      if (wf.id) {
        r = await fetch(`${API}/api/workflows/${wf.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(wf) });
      } else {
        r = await fetch(`${API}/api/workflows`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(wf) });
      }
      if (r.ok) {
        const saved = await r.json();
        setCurrent(saved);
        fetchWorkflows();
      }
    } catch (e) {
      setError(String(e));
    }
  };

  const addNode = (type: WorkflowNode["type"]) => {
    if (!current) newWorkflow();
    nodeCounter.current++;
    const cfg = NODE_TYPES[type];
    const node: WorkflowNode = {
      id: `node_${nodeCounter.current}`,
      type,
      label: cfg.label,
      x: 20 + (nodeCounter.current % 3) * 210,
      y: 20 + Math.floor(nodeCounter.current / 3) * 140,
      params: {},
    };
    setCurrent(prev => prev ? { ...prev, nodes: [...prev.nodes, node] } : prev);
  };

  const updateNodeParam = (nodeId: string, key: string, val: string) => {
    setCurrent(prev => prev ? {
      ...prev,
      nodes: prev.nodes.map(n => n.id === nodeId ? { ...n, params: { ...n.params, [key]: val } } : n),
    } : prev);
  };

  const runWorkflow = async () => {
    if (!current || !current.id) {
      setError("Save the workflow first before running.");
      return;
    }
    setRunning(true);
    setError("");
    const init: Record<string, NodeRunResult> = {};
    current.nodes.forEach(n => { init[n.id] = { node_id: n.id, status: "pending" }; });
    setRunResults(init);
    try {
      const r = await fetch(`${API}/api/workflows/${current.id}/run`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const results: Record<string, NodeRunResult> = {};
      (data.results || []).forEach((res: NodeRunResult) => { results[res.node_id] = res; });
      setRunResults(results);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const clearCanvas = () => {
    if (current) setCurrent({ ...current, nodes: [], edges: [] });
    setRunResults({});
    setSelectedNodeId(null);
  };

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif", color: "#f9fafb", height: "100%", overflowY: "auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "#e5e7eb" }}>Workflow Builder</h3>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={newWorkflow}
            style={{ background: "#1f2937", color: "#9ca3af", border: "1px solid #374151", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11 }}>
            + New
          </button>
          <select onChange={e => e.target.value && loadWorkflow(e.target.value)} defaultValue=""
            style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#9ca3af", padding: "4px 8px", fontSize: 11 }}>
            <option value="">Load saved…</option>
            {workflows.map(wf => <option key={wf.id} value={wf.id}>{wf.name}</option>)}
          </select>
        </div>
      </div>

      {!current ? (
        <div style={{ textAlign: "center", padding: 40, color: "#4b5563" }}>
          <p style={{ fontSize: 13 }}>Create a new workflow or load a saved one.</p>
          <p style={{ fontSize: 11 }}>Build multi-step AI generation pipelines by chaining Image Gen, Video Gen, and Lip Sync nodes.</p>
          <button onClick={newWorkflow}
            style={{ background: "#4f46e5", color: "#fff", border: "none", borderRadius: 6, padding: "8px 20px", cursor: "pointer", fontSize: 13, marginTop: 8 }}>
            Start Building
          </button>
        </div>
      ) : (
        <>
          {/* Toolbar */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <input value={savingName} onChange={e => setSavingName(e.target.value)} placeholder="Workflow name"
              style={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, color: "#f9fafb", padding: "5px 8px", fontSize: 12, width: 160 }} />
            <button onClick={saveWorkflow}
              style={{ background: "#1f2937", color: "#9ca3af", border: "1px solid #374151", borderRadius: 6, padding: "5px 10px", cursor: "pointer", fontSize: 11 }}>
              Save
            </button>
            <button onClick={runWorkflow} disabled={running}
              style={{ background: running ? "#374151" : "#065f46", color: running ? "#6b7280" : "#6ee7b7", border: "none", borderRadius: 6, padding: "5px 12px", cursor: running ? "not-allowed" : "pointer", fontSize: 11, fontWeight: 600 }}>
              {running ? "Running…" : "▶ Run"}
            </button>
            <button onClick={clearCanvas}
              style={{ background: "#1f2937", color: "#9ca3af", border: "1px solid #374151", borderRadius: 6, padding: "5px 10px", cursor: "pointer", fontSize: 11 }}>
              Clear
            </button>
          </div>

          {error && (
            <div style={{ background: "#450a0a", border: "1px solid #b91c1c", borderRadius: 6, padding: "6px 10px", fontSize: 11, color: "#fca5a5", marginBottom: 8 }}>
              {error}
            </div>
          )}

          {/* Canvas + palette */}
          <div style={{ display: "flex", gap: 10 }}>
            <NodePalette onAdd={addNode} />
            <div style={{ flex: 1, minHeight: 420 }}>
              <WorkflowCanvas
                nodes={current.nodes}
                edges={current.edges}
                selectedId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
                onParamChange={updateNodeParam}
                runResults={runResults}
              />
            </div>
          </div>

          {/* Run results summary */}
          {Object.keys(runResults).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 6px" }}>Run results</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
                {Object.values(runResults).map(res => (
                  <div key={res.node_id} style={{ background: "#111827", borderRadius: 6, padding: "8px 10px", border: "1px solid #1f2937" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>{res.node_id}</div>
                    {res.url ? (
                      res.url.match(/\.(mp4|webm|mov)$/i)
                        ? <video src={res.url} controls style={{ width: "100%", borderRadius: 4 }} />
                        : <img src={res.url} alt="" style={{ width: "100%", borderRadius: 4 }} />
                    ) : (
                      <div style={{ fontSize: 11, color: res.status === "error" ? "#fca5a5" : "#6b7280" }}>
                        {res.error || res.status}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
