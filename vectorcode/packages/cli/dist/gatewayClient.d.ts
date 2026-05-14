/**
 * Gateway client — talks to VectorCode's FastAPI gateway.
 * Endpoints: /run, /stream (SSE), /status, /health, /sessions, /sessions/{id}/cancel
 */
import type { GatewayEvent, RunRequest, RunResponse } from './types.js';
export interface GatewayConfig {
    baseUrl: string;
    timeout?: number;
}
export declare class GatewayClient {
    private baseUrl;
    private timeout;
    constructor(config: GatewayConfig);
    /** Check gateway health. */
    health(): Promise<{
        status: string;
        version?: string;
    }>;
    /** Get current status (active sessions, model, etc.). */
    status(): Promise<{
        status: string;
        active_sessions: number;
        total_sessions: number;
        version: string;
        uptime_seconds: number;
    }>;
    /** Synchronous run — wait for full response. */
    run(req: RunRequest): Promise<RunResponse>;
    /** Streaming run — yields events as they arrive (SSE). */
    stream(req: RunRequest, onEvent: (e: GatewayEvent) => void): {
        close: () => void;
    };
    /** Cancel a running session. */
    cancel(sessionId: string): Promise<void>;
    /** Reset a session's history. */
    reset(sessionId: string): Promise<void>;
    /** Compact a session's history. */
    compact(sessionId: string): Promise<{
        messages_before: number;
        messages_after: number;
    }>;
    /** Switch a session's model. */
    switchModel(sessionId: string, model: string): Promise<void>;
}
