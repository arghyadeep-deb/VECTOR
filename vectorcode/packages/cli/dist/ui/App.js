import React, { useState, useCallback } from "react";
import { Box, useApp } from "ink";
import { TopBar } from "./TopBar.js";
import { ChatPane } from "./ChatPane.js";
import { StatusLine } from "./StatusLine.js";
import { InputBar } from "./InputBar.js";
import { ModelsTable } from "./ModelsTable.js";
export function App({ verbose }) {
    const [messages, setMessages] = useState([]);
    const [model, setModel] = useState("vector-focus");
    const [mode, setMode] = useState("cautious");
    const [tokens, setTokens] = useState(0);
    const [cost, setCost] = useState("0.000000");
    const [showModels, setShowModels] = useState(false);
    const [processing, setProcessing] = useState(false);
    const { exit } = useApp();
    const handleSubmit = useCallback(async (input) => {
        if (input.startsWith("/")) {
            await handleCommand(input);
            return;
        }
        setProcessing(true);
        setMessages(prev => [...prev, { role: "user", content: input }]);
        // Simulate tool call for demo purposes
        setTimeout(() => {
            setMessages(prev => [...prev, {
                    role: "tool",
                    content: `src/auth.ts`,
                    toolName: "reading",
                }]);
        }, 500);
        setTimeout(() => {
            setMessages(prev => [...prev, {
                    role: "assistant",
                    content: `\x1b[92mI'll help with that.\x1b[0m\n\nLet me look into it. The ${input.slice(0, 30)}... task has been noted.`,
                }]);
            setTokens(prev => prev + input.length);
            setProcessing(false);
        }, 1500);
    }, []);
    const handleCommand = useCallback(async (cmd) => {
        const parts = cmd.trim().split(/\s+/);
        const verb = parts[0].toLowerCase();
        switch (verb) {
            case "/help":
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: [
                            "  Commands:",
                            "    /status        Session status",
                            "    /model <id>    Switch model (e.g. /model ollama/llama4:scout)",
                            "    /models        List configured providers with reachability",
                            "    /models <p>    Filter models by provider",
                            "    /providers     Show all 17 providers with status",
                            "    /apikey <p> <k> Set API key for a provider",
                            "    /mode <mode>   Set permission mode",
                            "    /memory        Show session memory",
                            "    /compact       Trigger context compaction",
                            "    /cost          Show token usage and estimated cost",
                            "    /diff          Show file changes this session",
                            "    /clear         Clear conversation history",
                            "    /spawn <task>  Spawn a worker agent",
                            "    /help          Show this help",
                            "    /quit          Exit Vector Code",
                        ].join("\n"),
                    }]);
                break;
            case "/models":
                setShowModels(true);
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: "",
                    }]);
                break;
            case "/providers":
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: "\x1b[96mFetching provider status...\x1b[0m",
                    }]);
                try {
                    const { cmdProviders } = await import("@vector-code/core");
                    const chunks = [];
                    const origLog = console.log;
                    console.log = (...args) => chunks.push(args.join(" "));
                    await cmdProviders();
                    console.log = origLog;
                    setMessages(prev => [...prev.slice(0, -1), {
                            role: "assistant",
                            content: chunks.join("\n"),
                        }]);
                }
                catch (e) {
                    setMessages(prev => [...prev.slice(0, -1), {
                            role: "assistant",
                            content: `\x1b[91mError: ${e.message}\x1b[0m`,
                        }]);
                }
                break;
            case "/apikey":
                {
                    const provider = parts[1];
                    const key = parts[2];
                    if (!provider || !key) {
                        setMessages(prev => [...prev, { role: "assistant", content: "\x1b[93mUsage: /apikey <provider> <key>\x1b[0m" }]);
                        break;
                    }
                    try {
                        const { setApiKey } = await import("@vector-code/core");
                        const extra = parts.length > 3 ? { accountId: parts[3] } : undefined;
                        setApiKey(provider, key, extra);
                        setMessages(prev => [...prev, { role: "assistant", content: `\x1b[92m${provider} API key saved\x1b[0m` }]);
                    }
                    catch (e) {
                        setMessages(prev => [...prev, { role: "assistant", content: `\x1b[91mError: ${e.message}\x1b[0m` }]);
                    }
                }
                break;
            case "/status":
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: [
                            `  model:   ${model}`,
                            `  mode:    ${mode}`,
                            `  tokens:  ${tokens} in/out total`,
                            `  uptime:  session active`,
                            `  verbose: ${verbose ? "on" : "off"}`,
                        ].join("\n"),
                    }]);
                break;
            case "/model":
                if (parts[1]) {
                    setModel(parts[1]);
                    setMessages(prev => [...prev, {
                            role: "assistant",
                            content: `\x1b[92mSwitched to ${parts[1]}\x1b[0m`,
                        }]);
                }
                break;
            case "/mode":
                if (parts[1]) {
                    setMode(parts[1]);
                    setMessages(prev => [...prev, {
                            role: "assistant",
                            content: `\x1b[92mMode → ${parts[1]}\x1b[0m`,
                        }]);
                }
                break;
            case "/quit":
            case "/exit":
                exit();
            case "/cost":
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: [
                            `  Tokens:  ${tokens} total`,
                            `  Cost:    $${cost} USD`,
                            `  Model:   ${model}`,
                        ].join("\n"),
                    }]);
                break;
            default:
                setMessages(prev => [...prev, {
                        role: "assistant",
                        content: `\x1b[93mUnknown command: ${verb}. Type /help for commands.\x1b[0m`,
                    }]);
        }
    }, [model, mode, tokens, cost, verbose]);
    return (React.createElement(Box, { flexDirection: "column", height: "100%" },
        React.createElement(TopBar, { model: model, mode: mode, tokens: tokens, cost: cost }),
        React.createElement(ChatPane, { messages: messages, height: 18 }),
        showModels && (React.createElement(ModelsTable, { activeModel: model })),
        React.createElement(StatusLine, { model: model, mode: mode, tokens: tokens, cost: cost }),
        React.createElement(InputBar, { onSubmit: handleSubmit, disabled: processing })));
}
//# sourceMappingURL=App.js.map