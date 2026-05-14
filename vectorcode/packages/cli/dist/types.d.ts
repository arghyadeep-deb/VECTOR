/**
 * Shared types for VectorCode TUI.
 * Mirrors the gateway's wire format from /run, /stream, /status endpoints.
 */
export type Role = 'user' | 'assistant' | 'tool' | 'system';
export interface ChatMessage {
    id: string;
    role: Role;
    content: string;
    timestamp: number;
    streaming?: boolean;
    toolName?: string;
    toolStatus?: 'running' | 'done' | 'failed';
    toolDurationMs?: number;
    toolArgs?: Record<string, unknown>;
}
export interface ToolEvent {
    id: string;
    name: string;
    args: Record<string, unknown>;
    status: 'running' | 'done' | 'failed';
    startedAt: number;
    finishedAt?: number;
    preview?: string;
    error?: string;
}
export interface SessionStatus {
    sessionId: string;
    model: string;
    mode: 'cautious' | 'standard' | 'autonomous' | 'read-only' | 'repl';
    online: boolean;
    modelsAvailable: number;
    iterationsUsed: number;
    iterationsMax: number;
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    costUsd: number;
    uptimeSeconds: number;
}
export interface GatewayEvent {
    type: 'start' | 'token' | 'tool_call' | 'tool_result' | 'thinking' | 'done' | 'error' | 'cancelled' | 'status';
    content?: string;
    sessionId?: string;
    name?: string;
    args?: Record<string, unknown>;
    callId?: string;
    result?: string;
    durationMs?: number;
    response?: string;
    iterations?: number;
    message?: string;
    status?: Partial<SessionStatus>;
}
export interface RunRequest {
    input: string;
    model?: string;
    sessionId?: string;
    projectDir?: string;
    mode?: SessionStatus['mode'];
    metadata?: Record<string, unknown>;
}
export interface RunResponse {
    sessionId: string;
    response: string;
    toolCallsMade: number;
    iterationsUsed: number;
    model: string;
    status: 'complete' | 'error' | 'cancelled' | 'max_iterations';
}
export interface SlashCommand {
    name: string;
    description: string;
    category?: string;
}
