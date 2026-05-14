/**
 * Gateway client — talks to VectorCode's FastAPI gateway.
 * Endpoints: /run, /stream (SSE), /status, /health, /sessions, /sessions/{id}/cancel
 */

import type {
  GatewayEvent,
  RunRequest,
  RunResponse,
  SessionStatus,
} from './types.js';

export interface GatewayConfig {
  baseUrl: string;
  timeout?: number;
}

export class GatewayClient {
  private baseUrl: string;
  private timeout: number;

  constructor(config: GatewayConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.timeout = config.timeout ?? 60000;
  }

  /** Check gateway health. */
  async health(): Promise<{ status: string; version?: string }> {
    const r = await fetch(`${this.baseUrl}/health`);
    if (!r.ok) throw new Error(`health check failed: HTTP ${r.status}`);
    return r.json() as Promise<{ status: string; version?: string }>;
  }

  /** Get current status (active sessions, model, etc.). */
  async status(): Promise<{
    status: string;
    active_sessions: number;
    total_sessions: number;
    version: string;
    uptime_seconds: number;
  }> {
    const r = await fetch(`${this.baseUrl}/status`);
    if (!r.ok) throw new Error(`status failed: HTTP ${r.status}`);
    return r.json() as Promise<{
      status: string;
      active_sessions: number;
      total_sessions: number;
      version: string;
      uptime_seconds: number;
    }>;
  }

  /** Synchronous run — wait for full response. */
  async run(req: RunRequest): Promise<RunResponse> {
    const ctrl = new AbortController();
    const timeoutId = setTimeout(() => ctrl.abort(), this.timeout);
    try {
      const r = await fetch(`${this.baseUrl}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input: req.input,
          model: req.model ?? '',
          session_id: req.sessionId ?? '',
          project_dir: req.projectDir ?? '.',
          mode: req.mode ?? 'standard',
          metadata: req.metadata ?? {},
        }),
        signal: ctrl.signal,
      });
      if (!r.ok) {
        const errText = await r.text();
        throw new Error(`run failed: HTTP ${r.status}: ${errText.slice(0, 200)}`);
      }
      const data = (await r.json()) as Record<string, unknown>;
      return {
        sessionId: String(data.session_id ?? ''),
        response: String(data.response ?? ''),
        toolCallsMade: Number(data.tool_calls_made ?? 0),
        iterationsUsed: Number(data.iterations_used ?? 0),
        model: String(data.model ?? ''),
        status: (data.status as RunResponse['status']) ?? 'complete',
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /** Streaming run — yields events as they arrive (SSE). */
  stream(req: RunRequest, onEvent: (e: GatewayEvent) => void): { close: () => void } {
    const url = `${this.baseUrl}/stream`;
    const body = JSON.stringify({
      input: req.input,
      model: req.model ?? '',
      session_id: req.sessionId ?? '',
      project_dir: req.projectDir ?? '.',
      mode: req.mode ?? 'standard',
      metadata: req.metadata ?? {},
    });

    // EventSource doesn't support POST natively, so we use fetch with manual SSE parsing
    const ctrl = new AbortController();

    (async () => {
      try {
        const r = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body,
          signal: ctrl.signal,
        });
        if (!r.ok || !r.body) {
          onEvent({ type: 'error', message: `HTTP ${r.status}` });
          return;
        }
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split(/\n\n/);
          buffer = events.pop() ?? '';
          for (const evt of events) {
            const dataLine = evt
              .split('\n')
              .find((l) => l.startsWith('data:'));
            if (!dataLine) continue;
            const payload = dataLine.slice(5).trim();
            if (!payload) continue;
            try {
              const parsed = JSON.parse(payload) as GatewayEvent;
              // Normalize snake_case to camelCase
              const normalized: GatewayEvent = {
                ...parsed,
                callId: (parsed as { call_id?: string }).call_id ?? parsed.callId,
                durationMs: (parsed as { duration_ms?: number }).duration_ms ?? parsed.durationMs,
                sessionId: (parsed as { session_id?: string }).session_id ?? parsed.sessionId,
              };
              onEvent(normalized);
            } catch {
              // ignore malformed
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          onEvent({ type: 'error', message: (err as Error).message });
        }
      }
    })();

    return { close: () => ctrl.abort() };
  }

  /** Cancel a running session. */
  async cancel(sessionId: string): Promise<void> {
    const r = await fetch(`${this.baseUrl}/sessions/${sessionId}/cancel`, {
      method: 'POST',
    });
    if (!r.ok) throw new Error(`cancel failed: HTTP ${r.status}`);
  }

  /** Reset a session's history. */
  async reset(sessionId: string): Promise<void> {
    const r = await fetch(`${this.baseUrl}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!r.ok) throw new Error(`reset failed: HTTP ${r.status}`);
  }

  /** Compact a session's history. */
  async compact(sessionId: string): Promise<{ messages_before: number; messages_after: number }> {
    const r = await fetch(`${this.baseUrl}/compact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!r.ok) throw new Error(`compact failed: HTTP ${r.status}`);
    return r.json() as Promise<{ messages_before: number; messages_after: number }>;
  }

  /** Switch a session's model. */
  async switchModel(sessionId: string, model: string): Promise<void> {
    const r = await fetch(`${this.baseUrl}/model`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, model }),
    });
    if (!r.ok) throw new Error(`switchModel failed: HTTP ${r.status}`);
  }
}
