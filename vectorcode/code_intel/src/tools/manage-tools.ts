// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 VECTOR - Altaire Limited

import { QDRANT_COLLECTION_PREFIX, QDRANT_HOST, QDRANT_MODE, QDRANT_PORT, QDRANT_URL, VECTORCODE_VERSION } from "../constants.js";
import { getArtifactStatusSummary } from "../services/context-artifacts.js";
import { isDockerAvailable, isQdrantImagePresent, isQdrantRunning } from "../services/docker.js";
import { getEmbeddingConfig } from "../services/embedding-config.js";
import { getEmbeddingProvider } from "../services/embedding-provider.js";
import { getGraphMetadata, getProjectMetadata, listCodebaseCollections } from "../services/qdrant.js";
import type { HealthStatus } from "../types.js";

/** Quick infrastructure check for embedding in vc_about */
async function getInfraStatusSummary(): Promise<string[]> {
  const lines: string[] = [];
  const config = getEmbeddingConfig();
  try {
    if (QDRANT_MODE === "external") {
      const endpoint = QDRANT_URL ?? `http://${QDRANT_HOST}:${QDRANT_PORT}`;
      try {
        await listCodebaseCollections(); // throws if unreachable
        const provider = await getEmbeddingProvider();
        const health = await provider.healthCheck();
        if (health.available) {
          lines.push(`Infrastructure: ✅ External Qdrant reachable (${endpoint}), ${config.embeddingProvider} embeddings ready`);
        } else {
          lines.push(`Infrastructure: ⚠️ External Qdrant reachable (${endpoint}), but ${config.embeddingProvider} embeddings not ready`);
        }
      } catch {
        lines.push(`Infrastructure: ❌ Cannot reach external Qdrant at ${endpoint}`);
        lines.push("  Check QDRANT_URL / QDRANT_HOST and make sure the server is running.");
      }
    } else {
      const docker = await isDockerAvailable();
      if (!docker) {
        lines.push("Infrastructure: ❌ Docker not available");
        lines.push("  Install from https://docker.com and start Docker Desktop.");
        return lines;
      }
      const qdrant = await isQdrantRunning();
      const provider = await getEmbeddingProvider();
      const health = await provider.healthCheck();
      if (qdrant && health.available) {
        lines.push(`Infrastructure: ✅ All services running (Docker, Qdrant, ${config.embeddingProvider} embeddings)`);
      } else {
        const missing: string[] = [];
        if (!qdrant) missing.push("Qdrant");
        if (!health.available) missing.push(`${config.embeddingProvider} embeddings`);
        lines.push(`Infrastructure: ⚠️ Docker OK, but ${missing.join(" and ")} not running`);
        lines.push("  Run vc_index or vc_health to auto-start services.");
      }
    }
  } catch {
    lines.push("Infrastructure: ❓ Could not check status");
  }
  return lines;
}

export async function handleManageTool(
  name: string,
  _args: Record<string, unknown>,
): Promise<string> {
  switch (name) {
    case "vc_health": {
      const config = getEmbeddingConfig();
      const status: HealthStatus = {
        docker: false,
        ollama: false,
        qdrant: false,
        ollamaModel: false,
        qdrantImage: false,
        ollamaImage: false,
      };

      const icon = (ok: boolean) => (ok ? "[OK]" : "[MISSING]");
      const lines: string[] = [
        "VectorCode Intelligence — Infrastructure Health Check:",
        "",
        `Qdrant mode: ${QDRANT_MODE}`,
      ];

      if (QDRANT_MODE === "external") {
        const endpoint = QDRANT_URL ?? `http://${QDRANT_HOST}:${QDRANT_PORT}`;
        lines.push(`Qdrant endpoint: ${endpoint}`);
        try {
          await listCodebaseCollections();
          status.qdrant = true;
          lines.push(`${icon(true)} External Qdrant (${endpoint}): Reachable`);
        } catch {
          lines.push(`${icon(false)} External Qdrant (${endpoint}): Unreachable — check QDRANT_URL / QDRANT_HOST`);
        }
      } else {
        // managed mode — Docker-managed container
        const docker = await isDockerAvailable();
        status.docker = docker;
        lines.push(`${icon(status.docker)} Docker: ${status.docker ? "Running" : "Not found — install from https://docker.com"}`);

        if (docker) {
          const [qdrantRunning, qdrantImage] = await Promise.all([
            isQdrantRunning(),
            isQdrantImagePresent(),
          ]);
          status.qdrant = qdrantRunning;
          status.qdrantImage = qdrantImage;

          lines.push(`${icon(status.qdrantImage)} Qdrant image: ${status.qdrantImage ? "Pulled" : "Not pulled — will be pulled on first index"}`);
          lines.push(`${icon(status.qdrant)} Qdrant container: ${status.qdrant ? "Running" : "Not running — will be started on first index"}`);
        }
      }

      // Embedding provider health check (works for ollama, openai, google)
      lines.push("");
      lines.push(`Embedding provider: ${config.embeddingProvider}`);
      const provider = await getEmbeddingProvider();
      const health = await provider.healthCheck();
      lines.push(...health.statusLines);

      lines.push("");
      if (QDRANT_MODE === "external") {
        lines.push("External Qdrant mode — Docker is not required for the vector database.");
      } else {
        lines.push(
          status.docker
            ? "Docker is available. Qdrant container will be auto-managed."
            : "Docker is required for Qdrant. Install from https://docker.com",
        );
      }

      return lines.join("\n");
    }

    case "vc_projects": {
      try {
        const collections = await listCodebaseCollections();

        if (collections.length === 0) {
          return "No projects have been indexed yet. Use vc_index to index a project.";
        }

        // All four references below honour QDRANT_COLLECTION_PREFIX so this
        // tool keeps working on shared Qdrant deployments where VectorCode Intelligence's
        // collection names carry an instance-specific prefix.
        const p = QDRANT_COLLECTION_PREFIX;
        const codebasePrefix = `${p}codebase_`;
        const graphPrefix = `${p}codegraph_`;
        const codebaseCollections = collections.filter((c) => c.startsWith(codebasePrefix));
        const graphCollections = collections.filter((c) => c.startsWith(graphPrefix));

        const lines = ["Indexed projects:\n"];

        for (const c of codebaseCollections) {
          const projectId = c.slice(codebasePrefix.length);
          const hasGraph = graphCollections.includes(`${graphPrefix}${projectId}`);
          const metadata = await getProjectMetadata(c);
          const pathInfo = metadata?.projectPath || "(path unknown — indexed before path tracking)";
          lines.push(`  - ${pathInfo}`);
          lines.push(`    Collection: ${c}`);
          if (metadata?.lastIndexedAt) {
            lines.push(`    Last indexed: ${metadata.lastIndexedAt}`);
          }
          if (metadata?.filesIndexed !== undefined) {
            if (metadata.indexingStatus === "in-progress") {
              lines.push(`    Files: ${metadata.filesIndexed}/${metadata.filesTotal} (INCOMPLETE — run vc_index to resume)`);
            } else {
              lines.push(`    Files: ${metadata.filesIndexed}`);
            }
          }
          if (hasGraph) {
            const graphMeta = await getGraphMetadata(`${graphPrefix}${projectId}`);
            if (graphMeta) {
              lines.push(`    Code graph: ${graphMeta.nodeCount} files, ${graphMeta.edgeCount} edges (built: ${graphMeta.lastBuiltAt})`);
            } else {
              lines.push(`    Code graph: present`);
            }
          } else {
            lines.push(`    Code graph: not built`);
          }
          // Context artifacts
          try {
            const pathInfo2 = metadata?.projectPath;
            if (pathInfo2) {
              const artifactSummary = await getArtifactStatusSummary(pathInfo2);
              if (artifactSummary) {
                lines.push(`    ${artifactSummary.lines[0]}`);
              }
            }
          } catch {
            // non-critical
          }
        }

        return lines.join("\n");
      } catch {
        return "Could not connect to Qdrant. Run vc_health to check infrastructure status.";
      }
    }

    case "vc_about": {
      const infraStatus = await getInfraStatusSummary();
      return [
        "VectorCode Intelligence — Codebase intelligence MCP server",
        "Hybrid semantic + keyword search, dependency graphs, context artifacts.",
        "",
        ...infraStatus,
        "",
        "━━━ Quick Reference ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Indexing:",
        "  vc_index        — Index a project (background). Poll with vc_status.",
        "  vc_update       — Incremental re-index (changed files only).",
        "  vc_stop         — Gracefully stop in-progress indexing.",
        "  vc_remove       — Delete a project's index.",
        "  vc_watch        — Start/stop/status of live file watcher.",
        "",
        "Search:",
        "  vc_search       — Hybrid semantic + BM25 search. Use after indexing.",
        "  vc_status       — Check index status, progress, watcher state.",
        "",
        "Dependency Graph:",
        "  vc_graph_build  — Build AST-based dependency graph (background).",
        "  vc_graph_query  — Imports & dependents for a file.",
        "  vc_graph_stats  — Graph stats: files, edges, most connected, orphans.",
        "  vc_graph_circular — Find circular dependencies.",
        "  vc_graph_visualize — Mermaid diagram (default) or interactive HTML explorer (mode=\"interactive\"), colour-coded by language.",
        "  vc_graph_status — Poll graph build progress.",
        "  vc_graph_remove — Delete a project's graph.",
        "",
        "Context Artifacts:",
        "  vc_context        — List artifacts (.vectorcode-artifacts.json).",
        "  vc_context_search — Search schemas, API specs, configs, docs.",
        "  vc_context_index  — Re-index artifacts (usually automatic).",
        "  vc_context_remove — Delete indexed artifacts.",
        "",
        "Management:",
        "  vc_health       — Check Docker, Qdrant, embeddings status.",
        "  vc_projects — List all indexed projects.",
        "",
        "━━━ Typical Workflow ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "1. vc_index → poll vc_status until complete.",
        "2. vc_search to find code. Search before reading files.",
        "3. vc_graph_query to explore dependencies.",
        "4. vc_context_search for schemas, API specs, configs.",
        "",
        `v${VECTORCODE_VERSION} · © 2026 VECTOR — Altaire Limited · AGPL-3.0`,
        "https://github.com/giancarloerra/vectorcode",
      ].join("\n");
    }

    default:
      return `Unknown tool: ${name}`;
  }
}
