/**
 * Main App component — top-level state, routing, and pane orchestration.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, useApp, useInput } from 'ink';
import { TopBar } from './ui/TopBar.js';
import { Banner } from './ui/Banner.js';
import { ChatPane } from './ui/ChatPane.js';
import { ToolPane } from './ui/ToolPane.js';
import { InputBar } from './ui/InputBar.js';
import { StatusLine } from './ui/StatusLine.js';
import { GatewayClient } from './gatewayClient.js';
import { SLASH_COMMANDS } from './slashCommands.js';
export const App = ({ gatewayUrl, initialModel = 'vector-focus', initialMode = 'standard', showBanner = true, }) => {
    const { exit } = useApp();
    const clientRef = useRef(null);
    const streamRef = useRef(null);
    const [messages, setMessages] = useState([]);
    const [toolEvents, setToolEvents] = useState([]);
    const [busy, setBusy] = useState(false);
    const [thinking, setThinking] = useState(false);
    const [sessionStatus, setSessionStatus] = useState({
        model: initialModel,
        mode: initialMode,
        online: false,
        iterationsUsed: 0,
        iterationsMax: 90,
    });
    const [gatewayHealthy, setGatewayHealthy] = useState(false);
    const [showToolPane, setShowToolPane] = useState(true);
    const [bannerDismissed, setBannerDismissed] = useState(!showBanner);
    const [sessionId, setSessionId] = useState('');
    // Initialize client
    useEffect(() => {
        clientRef.current = new GatewayClient({ baseUrl: gatewayUrl });
        void (async () => {
            try {
                await clientRef.current.health();
                setGatewayHealthy(true);
                setSessionStatus((s) => ({ ...s, online: true }));
            }
            catch {
                setGatewayHealthy(false);
            }
        })();
    }, [gatewayUrl]);
    // Heartbeat: re-check gateway health every 10s
    useEffect(() => {
        const id = setInterval(async () => {
            if (!clientRef.current)
                return;
            try {
                await clientRef.current.health();
                setGatewayHealthy(true);
            }
            catch {
                setGatewayHealthy(false);
            }
        }, 10000);
        return () => clearInterval(id);
    }, []);
    // Global keys: Tab toggles tool pane, Ctrl+C cancels current run
    useInput((input, key) => {
        if (key.tab) {
            setShowToolPane((v) => !v);
            return;
        }
        if (key.ctrl && input === 'c') {
            if (busy && streamRef.current) {
                streamRef.current.close();
                streamRef.current = null;
                setBusy(false);
                setThinking(false);
                addMessage({
                    id: makeId(),
                    role: 'system',
                    content: 'cancelled',
                    timestamp: Date.now(),
                });
            }
        }
    });
    const addMessage = useCallback((m) => {
        setMessages((prev) => [...prev, m].slice(-1000));
    }, []);
    const updateLastAssistant = useCallback((delta) => {
        setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant' && last.streaming) {
                next[next.length - 1] = { ...last, content: last.content + delta };
            }
            else {
                next.push({
                    id: makeId(),
                    role: 'assistant',
                    content: delta,
                    timestamp: Date.now(),
                    streaming: true,
                });
            }
            return next;
        });
    }, []);
    const finalizeStreaming = useCallback(() => {
        setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
    }, []);
    const handleEvent = useCallback((e) => {
        switch (e.type) {
            case 'start':
                if (e.sessionId)
                    setSessionId(e.sessionId);
                setThinking(true);
                break;
            case 'thinking':
                setThinking(true);
                break;
            case 'token':
                setThinking(false);
                if (e.content)
                    updateLastAssistant(e.content);
                break;
            case 'tool_call':
                {
                    const id = e.callId ?? makeId();
                    const ev = {
                        id,
                        name: e.name ?? 'unknown',
                        args: e.args ?? {},
                        status: 'running',
                        startedAt: Date.now(),
                    };
                    setToolEvents((prev) => [...prev, ev].slice(-200));
                    addMessage({
                        id,
                        role: 'tool',
                        content: '',
                        timestamp: Date.now(),
                        toolName: e.name,
                        toolArgs: e.args,
                        toolStatus: 'running',
                    });
                }
                break;
            case 'tool_result':
                {
                    const id = e.callId;
                    const finishedAt = Date.now();
                    setToolEvents((prev) => prev.map((t) => t.id === id
                        ? {
                            ...t,
                            status: 'done',
                            finishedAt,
                            preview: (e.result || '').slice(0, 80),
                        }
                        : t));
                    setMessages((prev) => prev.map((m) => m.id === id
                        ? {
                            ...m,
                            content: e.result || '',
                            toolStatus: 'done',
                            toolDurationMs: e.durationMs,
                        }
                        : m));
                }
                break;
            case 'done':
                finalizeStreaming();
                setThinking(false);
                setBusy(false);
                streamRef.current = null;
                if (e.iterations !== undefined) {
                    setSessionStatus((s) => ({
                        ...s,
                        iterationsUsed: (s.iterationsUsed ?? 0) + (e.iterations ?? 0),
                    }));
                }
                break;
            case 'error':
                finalizeStreaming();
                setThinking(false);
                setBusy(false);
                streamRef.current = null;
                addMessage({
                    id: makeId(),
                    role: 'system',
                    content: `error: ${e.message ?? 'unknown'}`,
                    timestamp: Date.now(),
                });
                break;
            case 'cancelled':
                finalizeStreaming();
                setThinking(false);
                setBusy(false);
                streamRef.current = null;
                break;
        }
    }, [addMessage, finalizeStreaming, updateLastAssistant]);
    const handleSubmit = useCallback(async (input) => {
        // Local slash commands
        if (input === '/quit' || input === '/exit') {
            exit();
            return;
        }
        if (input === '/clear') {
            setMessages([]);
            setToolEvents([]);
            return;
        }
        if (input === '/help') {
            addMessage({
                id: makeId(),
                role: 'system',
                content: 'Slash commands:\n' +
                    SLASH_COMMANDS.map((c) => `  /${c.name.padEnd(14)} ${c.description}`).join('\n'),
                timestamp: Date.now(),
            });
            return;
        }
        if (input === '/status') {
            addMessage({
                id: makeId(),
                role: 'system',
                content: `model: ${sessionStatus.model}\n` +
                    `mode: ${sessionStatus.mode}\n` +
                    `gateway: ${gatewayHealthy ? 'online' : 'offline'}\n` +
                    `iterations: ${sessionStatus.iterationsUsed}/${sessionStatus.iterationsMax}\n` +
                    `tokens: ${(sessionStatus.inputTokens ?? 0) + (sessionStatus.outputTokens ?? 0)}\n` +
                    `cost: $${(sessionStatus.costUsd ?? 0).toFixed(4)}`,
                timestamp: Date.now(),
            });
            return;
        }
        // Push user message
        const userMsg = {
            id: makeId(),
            role: 'user',
            content: input,
            timestamp: Date.now(),
        };
        addMessage(userMsg);
        if (!clientRef.current)
            return;
        if (!gatewayHealthy) {
            addMessage({
                id: makeId(),
                role: 'system',
                content: 'gateway offline — start it with: vector gateway start',
                timestamp: Date.now(),
            });
            return;
        }
        // Start streaming
        setBusy(true);
        setThinking(true);
        streamRef.current = clientRef.current.stream({
            input,
            model: sessionStatus.model,
            sessionId,
            mode: sessionStatus.mode,
        }, handleEvent);
    }, [
        addMessage,
        exit,
        gatewayHealthy,
        handleEvent,
        sessionId,
        sessionStatus.iterationsMax,
        sessionStatus.iterationsUsed,
        sessionStatus.model,
        sessionStatus.mode,
        sessionStatus.costUsd,
        sessionStatus.inputTokens,
        sessionStatus.outputTokens,
    ]);
    // Layout
    return (React.createElement(Box, { flexDirection: "column", minHeight: 20 },
        React.createElement(TopBar, { status: sessionStatus, gatewayHealthy: gatewayHealthy }),
        !bannerDismissed && messages.length === 0 && (React.createElement(Banner, { cwd: process.cwd() })),
        React.createElement(Box, { flexGrow: 1, flexDirection: "row" },
            React.createElement(ChatPane, { messages: messages, thinking: thinking }),
            showToolPane && React.createElement(ToolPane, { events: toolEvents })),
        React.createElement(InputBar, { onSubmit: (v) => {
                setBannerDismissed(true);
                void handleSubmit(v);
            }, busy: busy, slashCommands: SLASH_COMMANDS, modelLabel: (sessionStatus.model ?? 'vector').replace('ollama/', ''), modeLabel: sessionStatus.mode ?? 'standard' }),
        React.createElement(StatusLine, { iterationsUsed: sessionStatus.iterationsUsed ?? 0, iterationsMax: sessionStatus.iterationsMax ?? 90, busy: busy })));
};
let _idCounter = 0;
function makeId() {
    _idCounter += 1;
    return `${Date.now().toString(36)}-${_idCounter.toString(36)}`;
}
//# sourceMappingURL=App.js.map