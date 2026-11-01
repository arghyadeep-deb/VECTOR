import React, { useState, useEffect, useRef } from 'react';
import { Box, Text, useApp, useInput, useStdout } from 'ink';
import TextInput from 'ink-text-input';
import SelectInput from 'ink-select-input';
import Spinner from 'ink-spinner';
import { LocalClient } from './localClient.js';
import { TopBar } from './ui/TopBar.js';
import { Banner } from './ui/Banner.js';
import { ChatPane } from './ui/ChatPane.js';
import { ToolPane } from './ui/ToolPane.js';
import { InputBar } from './ui/InputBar.js';
import { StatusLine } from './ui/StatusLine.js';
import { theme, applySkin } from './ui/theme.js';
let sequence = 0;
const id = () => String(++sequence);
export function App({ initialModel = 'vector-focus', initialMode = 'standard', python, resumeSession, editorContextFile, createClient = (listener) => new LocalClient(listener, python), }) {
    const { exit } = useApp();
    const { stdout, write } = useStdout();
    const [size, setSize] = useState({ width: stdout.columns || 100, height: stdout.rows || 30 });
    const [messages, setMessages] = useState([]);
    const [tools, setTools] = useState([]);
    const [status, setStatus] = useState({ model: initialModel, mode: initialMode });
    const [online, setOnline] = useState(false);
    const [busy, setBusy] = useState(false);
    const [stopping, setStopping] = useState(false);
    const [exiting, setExiting] = useState(false);
    const pendingExit = useRef(false);
    const [activity, setActivity] = useState(false);
    const [statusbar, setStatusbar] = useState(true);
    const [attachment, setAttachment] = useState();
    const [images, setImages] = useState([]);
    const pendingImageRun = useRef();
    const attachmentDraft = useRef('');
    const pendingEditorRun = useRef();
    const [insertion, setInsertion] = useState();
    const [offset, setOffset] = useState(0);
    const [approval, setApproval] = useState(null);
    const approvalRef = useRef(null);
    const [activeWorkers, setActiveWorkers] = useState(0);
    const activeWorkersRef = useRef(0);
    const workerStreams = useRef(new Map());
    const [models, setModels] = useState(null);
    const [modePicker, setModePicker] = useState(false);
    const [modelsLoading, setModelsLoading] = useState(false);
    const modelsPending = useRef(false);
    const [keyProvider, setKeyProvider] = useState('');
    const [keyDraft, setKeyDraft] = useState('');
    const [commandMenu, setCommandMenu] = useState({ items: [], selected: 0 });
    const [commands, setCommands] = useState([]);
    const [promptHistory, setPromptHistory] = useState([]);
    const client = useRef();
    const busyRef = useRef(false);
    const streamingId = useRef(null);
    const add = (role, content) => setMessages(previous => [...previous, { id: id(), role, content, timestamp: Date.now() }].slice(-1000));
    const updateApproval = (value) => { approvalRef.current = value; setApproval(value); };
    const finishExit = () => {
        if (pendingExit.current && !busyRef.current && activeWorkersRef.current === 0)
            exit();
    };
    useEffect(() => {
        const resize = () => setSize({ width: stdout.columns || 100, height: stdout.rows || 30 });
        stdout.on('resize', resize);
        client.current = createClient(event => {
            if (event.workerName) {
                const worker = event.workerName;
                if (event.activeWorkers !== undefined) {
                    activeWorkersRef.current = event.activeWorkers;
                    setActiveWorkers(event.activeWorkers);
                }
                if (event.type === 'approval') {
                    updateApproval(event);
                    setOffset(0);
                    return;
                }
                if (event.type === 'token' && event.content) {
                    const first = !workerStreams.current.has(worker);
                    if (first)
                        workerStreams.current.set(worker, id());
                    const tokenId = workerStreams.current.get(worker);
                    setMessages(previous => first ? [...previous, { id: tokenId, role: 'assistant',
                            content: `[Worker ${worker}]\n${event.content}`, timestamp: Date.now(), streaming: true }]
                        : previous.map(message => message.id === tokenId
                            ? { ...message, content: message.content + event.content } : message));
                    return;
                }
                if (event.type === 'worker_status') {
                    const terminal = ['completed', 'failed', 'cancelled'].includes(event.workerState || '');
                    if (terminal) {
                        const tokenId = workerStreams.current.get(worker);
                        if (tokenId)
                            setMessages(previous => event.workerState === 'completed'
                                ? previous.filter(message => message.id !== tokenId)
                                : previous.map(message => message.id === tokenId
                                    ? { ...message, streaming: false, content: message.content + `\n[Incomplete worker response: ${event.workerState}.]` }
                                    : message));
                        workerStreams.current.delete(worker);
                        if (approvalRef.current?.workerName === worker)
                            updateApproval(null);
                        add(event.workerState === 'completed' ? 'assistant' : 'system', `[Worker ${worker} · ${event.workerState}]\n${[event.result, event.message].filter(Boolean).join('\n') || '(No result returned.)'}`);
                    }
                    else
                        add('system', `[Worker ${worker} · ${event.workerState || 'running'}]`);
                    finishExit();
                    return;
                }
                if (event.type === 'notice' || event.type === 'error') {
                    add('system', `[Worker ${worker}] ${event.message || ''}`);
                    return;
                }
                if (event.type === 'tool_call' || event.type === 'tool_result') {
                    event = { ...event, name: `[${worker}] ${event.name || 'tool'}` };
                }
                else
                    return;
            }
            if (event.type === 'ready') {
                setOnline(true);
                if (resumeSession)
                    client.current?.send({ command: 'resume', session: resumeSession, projectDir: process.cwd() });
                if (editorContextFile)
                    client.current?.send({ command: 'editor_context', file: editorContextFile, projectDir: process.cwd() });
                client.current?.send({ command: 'commands' });
            }
            if (event.type === 'commands')
                setCommands(event.commands || []);
            if (event.imageAttachments !== undefined) {
                setImages(event.imageAttachments);
                if (pendingImageRun.current && !pendingImageRun.current.images.every(image => event.imageAttachments.some(pending => pending.id === image.id))) {
                    pendingImageRun.current = undefined;
                    pendingEditorRun.current = undefined;
                }
            }
            if (event.type === 'image_attachments' && event.status)
                setStatus(previous => ({ ...previous, ...event.status }));
            if (event.type === 'editor_context' && event.editorContext && event.question !== undefined) {
                if (event.editorContext.workspace === process.cwd()) {
                    setAttachment(event.editorContext);
                    attachmentDraft.current = event.question;
                    setInsertion({ id: id(), text: event.question });
                    add('system', 'Editor excerpt attached for one ordinary turn. Review the question before Enter. Submitted source stays in the normal transcript.');
                }
                else
                    add('system', 'Editor context belongs to another workspace and was not attached.');
            }
            if (event.type === 'start') {
                streamingId.current = null;
                if (!pendingImageRun.current)
                    pendingEditorRun.current = undefined;
            }
            let rejectedDraft;
            if (event.type === 'error' && pendingEditorRun.current) {
                setAttachment(pendingEditorRun.current.context);
                rejectedDraft = pendingEditorRun.current.draft;
                pendingEditorRun.current = undefined;
            }
            if (event.type === 'error' && pendingImageRun.current) {
                rejectedDraft = pendingImageRun.current.draft;
                pendingImageRun.current = undefined;
            }
            if (event.type === 'offline') {
                if (pendingImageRun.current)
                    rejectedDraft = pendingImageRun.current.draft;
                pendingImageRun.current = undefined;
                setImages([]);
            }
            if (rejectedDraft !== undefined) {
                attachmentDraft.current = rejectedDraft;
                setInsertion({ id: id(), text: rejectedDraft });
            }
            if (event.type === 'token' && event.content) {
                const first = !streamingId.current;
                if (first)
                    streamingId.current = id();
                const tokenId = streamingId.current;
                setMessages(previous => first ? [...previous, { id: tokenId, role: 'assistant', content: event.content,
                        timestamp: Date.now(), streaming: true }] : previous.map(message => message.id === tokenId
                    ? { ...message, content: message.content + event.content } : message));
            }
            if (event.type === 'offline') {
                setOnline(false);
                add('system', event.message || 'Engine offline.');
                if (pendingExit.current) {
                    pendingExit.current = false;
                    setExiting(false);
                    add('system', 'Shutdown could not be verified after disconnection. Completed actions have not been undone.');
                }
                if (activeWorkersRef.current > 0) {
                    add('system', 'Engine disconnected; worker result unverified. Completed actions have not been undone.');
                }
                const interrupted = new Set(workerStreams.current.values());
                setMessages(previous => previous.map(message => interrupted.has(message.id)
                    ? { ...message, streaming: false, content: message.content + '\n[Engine disconnected; worker result unverified.]' }
                    : message));
                workerStreams.current.clear();
                activeWorkersRef.current = 0;
                setActiveWorkers(0);
            }
            if (event.type === 'approval') {
                updateApproval(event);
                setOffset(0);
            }
            if (event.type === 'models' && modelsPending.current) {
                modelsPending.current = false;
                setModelsLoading(false);
                setModels(event.models || []);
            }
            if (event.type === 'notice') {
                add('system', event.message || '');
                if (event.status)
                    setStatus(previous => ({ ...previous, ...event.status }));
            }
            if (event.type === 'cancelling') {
                setStopping(true);
                updateApproval(null);
            }
            if (event.type === 'tool_call')
                setTools(previous => [...previous, {
                        id: id(), name: event.name || 'tool', args: event.args || {}, status: 'running', startedAt: Date.now(),
                    }].slice(-100));
            if (event.type === 'tool_result')
                setTools(previous => {
                    const next = [...previous];
                    let index = next.length - 1;
                    while (index >= 0 && (next[index].name !== event.name || next[index].status !== 'running'))
                        index--;
                    if (index >= 0)
                        next[index] = { ...next[index], status: /error|BLOCKED/i.test(event.result || '') ? 'failed' : 'done',
                            preview: event.result, finishedAt: Date.now() };
                    return next;
                });
            if (event.type === 'done' || event.type === 'command_result') {
                if (streamingId.current) {
                    const tokenId = streamingId.current;
                    setMessages(previous => previous.filter(message => message.id !== tokenId));
                    streamingId.current = null;
                }
                if (event.composerText !== undefined)
                    setInsertion({ id: id(), text: event.composerText });
                if (event.display?.statusbar !== undefined)
                    setStatusbar(event.display.statusbar);
                if (event.display?.verbose !== undefined)
                    setActivity(event.display.verbose);
                if (event.display?.colors)
                    applySkin(event.display.colors);
                if (event.history) {
                    const history = event.history.filter(message => ['user', 'assistant', 'tool'].includes(message.role))
                        .map(message => ({ ...message, id: id(), timestamp: Date.now() }));
                    const activeStreamIds = new Set(workerStreams.current.values());
                    setMessages(previous => [...history, ...previous.filter(message => activeStreamIds.has(message.id))]);
                }
                add(event.type === 'done' || event.replyRole === 'assistant' ? 'assistant' : 'system', event.response || '(No output returned.)');
                if (event.status)
                    setStatus(previous => ({ ...previous, ...event.status }));
            }
            if (event.type === 'error')
                add('system', event.message || 'The turn failed.');
            if (['error', 'cancelled', 'offline'].includes(event.type) && streamingId.current) {
                const tokenId = streamingId.current;
                setMessages(previous => previous.map(message => message.id === tokenId
                    ? { ...message, streaming: false, content: message.content + '\n[Incomplete response: turn interrupted.]' } : message));
                streamingId.current = null;
            }
            if (['done', 'command_result', 'error', 'cancelled', 'offline'].includes(event.type)) {
                setBusy(false);
                busyRef.current = false;
                setStopping(false);
                if (event.type === 'offline' || !approvalRef.current?.workerName)
                    updateApproval(null);
                if (modelsPending.current) {
                    modelsPending.current = false;
                    setModelsLoading(false);
                    setModels(null);
                }
                if (event.type === 'cancelled')
                    add('system', 'Stopped. Completed actions have not been undone.');
                finishExit();
            }
        });
        return () => { stdout.off('resize', resize); client.current?.close(); };
    }, []);
    useInput((input, key) => {
        if (key.ctrl && input === 'd' && !approval && !models && !modePicker && !keyProvider) {
            if (busyRef.current || activeWorkersRef.current > 0) {
                add('system', 'Wait for active work to finish before detaching pending context.');
            }
            else {
                setAttachment(undefined);
                if (images.length) {
                    busyRef.current = true;
                    setBusy(true);
                    client.current?.send({ command: 'slash', input: '/image clear', model: status.model,
                        mode: status.mode, projectDir: process.cwd() });
                }
                else
                    add('system', 'Editor excerpt detached.');
            }
        }
        if (key.escape) {
            if (modePicker)
                setModePicker(false);
            else if (models) {
                modelsPending.current = false;
                setModelsLoading(false);
                setModels(null);
            }
            else if (keyProvider) {
                setKeyDraft('');
                setKeyProvider('');
            }
            else if (commandMenu.items.length)
                return;
            else if (busyRef.current || activeWorkersRef.current > 0)
                client.current?.cancel();
        }
        if (key.tab && !approval && !models && !modePicker && !keyProvider && !commandMenu.items.length)
            setActivity(previous => !previous);
        if (key.pageUp)
            setOffset(previous => previous + Math.max(3, size.height - 14));
        if (key.pageDown)
            setOffset(previous => Math.max(0, previous - Math.max(3, size.height - 14)));
        if (key.ctrl && input === 'c') {
            if (busyRef.current || activeWorkersRef.current > 0)
                client.current?.cancel();
            else
                exit();
        }
    });
    const submit = (value) => {
        if (pendingExit.current)
            return;
        let text = value.trim();
        if (text)
            setPromptHistory(previous => previous[previous.length - 1] === text ? previous : [...previous, text].slice(-200));
        if (text.startsWith('/')) {
            const name = text.split(/\s/, 1)[0].slice(1);
            const entry = commands.find(command => command.name === name);
            if (!entry) {
                add('system', 'Unknown command. Use /help.');
                return false;
            }
            if (entry.available === false) {
                add('system', entry.reason || 'This command is unavailable in the local runtime.');
                return false;
            }
            text = '/' + (entry.canonical || entry.name) + text.slice(name.length + 1);
        }
        if (activeWorkersRef.current > 0 && /^\/(?:new|clear|model|models|mode)(?:\s|$)/.test(text)) {
            add('system', 'Wait for workers to finish or use /stop before changing the root session, model, or mode.');
            return attachment ? false : undefined;
        }
        if (text === '/quit') {
            if (busyRef.current || activeWorkersRef.current > 0) {
                pendingExit.current = true;
                setExiting(true);
                client.current?.cancel();
            }
            else
                exit();
            return;
        }
        if (text === '/stop') {
            if (busyRef.current || activeWorkersRef.current > 0)
                client.current?.cancel();
            else
                add('system', 'No active operation to stop.');
            return;
        }
        if (text === '/help' || text.startsWith('/help ')) {
            const query = text.slice(5).trim().toLowerCase().replace(/^\//, '');
            const exact = commands.find(command => command.name === query);
            const found = query === 'all' ? commands : exact ? [exact] : query
                ? commands.filter(command => (command.name + ' ' + command.description).toLowerCase().includes(query))
                : commands.filter(command => command.kind !== 'prompt' && command.available !== false);
            add('system', (found.length ? found.map(command => '/' + command.name + ' — ' + command.description +
                (command.available === false ? ' [unavailable: ' + command.reason + ']' : '')).join('\n') +
                `\n${commands.filter(command => command.kind === 'prompt').length} prompt workflows; ` +
                `${commands.filter(command => command.available === false).length} unavailable entries.`
                : 'No matching command.') + '\n/help <name> or /help all · / opens the catalog · PgUp/PgDn scroll');
            setOffset(0);
            return;
        }
        if (text === '/new' || text === '/clear') {
            client.current?.send({ command: 'reset', model: status.model, mode: status.mode });
            setMessages([]);
            setTools([]);
            setOffset(0);
            setStatus(previous => ({ ...previous, title: '', inputTokens: 0, outputTokens: 0 }));
            return;
        }
        if (text === '/models' || text === '/model') {
            modelsPending.current = true;
            setModelsLoading(true);
            setModels([]);
            client.current?.send({ command: 'models' });
            return;
        }
        if (text.startsWith('/model ')) {
            const model = text.slice(7).trim();
            if (model && !/\s/.test(model)) {
                setStatus(previous => ({ ...previous, model }));
                add('system', 'Selected ' + model);
            }
            return;
        }
        if (text === '/connect') {
            add('system', 'Use /connect openai (or anthropic, groq, deepseek, openrouter, mistral).');
            return;
        }
        if (text.startsWith('/connect ')) {
            const provider = text.slice(9).trim().toLowerCase();
            if (!/^[a-z][a-z0-9_-]*$/.test(provider)) {
                add('system', 'Enter only the provider name; paste keys into the secure dialog.');
                return;
            }
            setKeyProvider(provider);
            return;
        }
        if (text.startsWith('/mode ')) {
            const mode = text.slice(6).trim();
            if (['cautious', 'standard', 'read-only'].includes(mode))
                setStatus(previous => ({ ...previous, mode: mode }));
            else
                add('system', 'Modes: cautious, standard, read-only. Every proposed tool still asks for approval.');
            return;
        }
        if (text === '/mode') {
            setModePicker(true);
            return;
        }
        if (text === '/redraw') {
            write('\x1b[2J\x1b[H');
            return;
        }
        if (text.startsWith('/')) {
            if (!online || busyRef.current)
                return false;
            busyRef.current = true;
            setBusy(true);
            setOffset(0);
            client.current?.send({ command: 'slash', input: text, model: status.model, mode: status.mode, projectDir: process.cwd() });
            return;
        }
        if (!online || busyRef.current) {
            add('system', 'Wait for the local engine to be ready. Your draft is not submitted.');
            return false;
        }
        const model = status.model || initialModel;
        if ((images.length || status.localImages) && model.includes('/') && model.split('/', 1)[0].toLowerCase() !== 'ollama') {
            add('system', 'Image conversations require an Ollama model; select a vision model for pixels. Your draft was retained.');
            return false;
        }
        busyRef.current = true;
        setBusy(true);
        setOffset(0);
        add('user', text + images.map(image => `\n[Image: ${image.name}]`).join(''));
        client.current?.run({ input: text, model: status.model, mode: status.mode, projectDir: process.cwd(),
            ...(images.length ? { imageIds: images.map(image => image.id) } : {}),
            ...(attachment ? { editorContext: attachment } : {}) });
        if (images.length)
            pendingImageRun.current = { images, draft: value };
        if (attachment) {
            pendingEditorRun.current = { context: attachment, draft: value };
            setAttachment(undefined);
        }
        attachmentDraft.current = '';
    };
    const submitDraft = (value) => {
        const result = submit(value);
        if (result === false)
            return false;
        if ((attachment || images.length) && value.trim().startsWith('/'))
            return attachmentDraft.current;
    };
    const attachmentLabel = attachment || images.length ? {
        location: [attachment ? `Attached ${attachment.path}:${attachment.range.startLine}:${attachment.range.startColumn}-${attachment.range.endLine}:${attachment.range.endColumn}` : '',
            ...images.map(image => `Image ${image.name} (${image.width}x${image.height})`)].filter(Boolean).join(' · '),
        size: [attachment ? `${Array.from(attachment.text).length} chars` : '', images.length ? `${images.length} image${images.length === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · '),
    } : undefined;
    const showTools = activity && size.width >= 100;
    const screenHeight = Math.max(1, size.height - 2);
    const contentHeight = Math.max(4, screenHeight - 12);
    const chatWidth = size.width - (showTools ? 32 : 0);
    const modal = Boolean(approval || models || modePicker || keyProvider);
    const menuRows = !modal && commandMenu.items.length ? Math.min(6, contentHeight - 1, commandMenu.items.length) : 0;
    const chatHeight = contentHeight - (menuRows ? menuRows + 1 : 0);
    const menuStart = Math.max(0, Math.min(commandMenu.selected - menuRows + 1, commandMenu.items.length - menuRows));
    if (size.width < 48 || size.height < 18)
        return React.createElement(Box, null,
            React.createElement(Text, null, "Resize terminal to at least 48 columns \u00D7 18 rows. Ctrl+C exits."));
    return React.createElement(Box, { width: size.width, height: screenHeight, flexDirection: "column", overflow: "hidden" },
        React.createElement(TopBar, { status: status, gatewayHealthy: online }),
        React.createElement(Box, { height: contentHeight, overflow: "hidden" },
            React.createElement(Box, { width: chatWidth, flexDirection: "column" },
                approval ? React.createElement(ChatPane, { messages: [{ id: 'approval-details', role: 'system', timestamp: 0,
                            content: `${approval.workerName ? `Worker ${approval.workerName}\n` : ''}Review ${approval.name}\n${JSON.stringify(approval.args, null, 2)}` }], width: chatWidth, height: contentHeight, offset: offset })
                    : chatHeight > 0 ? messages.length ? React.createElement(ChatPane, { messages: messages, width: chatWidth, height: chatHeight, offset: offset })
                        : React.createElement(Banner, { model: status.model, height: chatHeight }) : null,
                menuRows > 0 && React.createElement(Box, { height: menuRows + 1, paddingX: 2, flexDirection: "column", overflow: "hidden" },
                    React.createElement(Text, { color: theme.brand, bold: true },
                        "Commands \u00B7 ",
                        commandMenu.selected + 1,
                        "/",
                        commandMenu.items.length),
                    commandMenu.items.slice(menuStart, menuStart + menuRows).map((command, index) => React.createElement(Box, { key: command.name, height: 1 },
                        React.createElement(Text, { color: theme.brand, inverse: menuStart + index === commandMenu.selected }, (menuStart + index === commandMenu.selected ? '› ' : '  ') + ('/' + command.name).padEnd(12)),
                        React.createElement(Text, { color: theme.dim, wrap: "truncate-end" },
                            " ",
                            command.description))))),
            showTools && React.createElement(ToolPane, { events: tools, width: 32 })),
        React.createElement(Box, { height: 1, paddingX: 2 },
            React.createElement(Text, { color: busy ? theme.warning : theme.dim }, exiting ? 'Stopping before exit; waiting for active operations…' : busy ? React.createElement(React.Fragment, null,
                React.createElement(Spinner, { type: "dots" }),
                " ",
                stopping ? 'Stopping after current operation…' : approval ? 'Waiting for your approval' : 'Working on your request…') : online ? commands.length ? 'Ready' : 'Loading commands…' : 'Starting local engine…')),
        modal ? React.createElement(Box, { height: 8, paddingX: 2, flexDirection: "column", borderStyle: "round", borderColor: theme.warning },
            approval && React.createElement(React.Fragment, null,
                approval.workerName && React.createElement(Text, { color: theme.brand },
                    "Worker ",
                    approval.workerName),
                React.createElement(Text, { bold: true, color: theme.warning },
                    "Allow ",
                    approval.name,
                    "?"),
                React.createElement(Text, { color: theme.dim }, "Review arguments above \u00B7 PgUp/PgDn scroll \u00B7 select an answer below"),
                React.createElement(SelectInput, { items: [{ label: 'Deny', value: false }, { label: 'Allow once', value: true }], onSelect: item => { client.current?.approve(approval.id, item.value); updateApproval(null); } })),
            models && React.createElement(React.Fragment, null,
                React.createElement(Text, { color: theme.brand }, "Choose model \u00B7 Esc closes \u00B7 /model accepts another model ID"),
                modelsLoading ? React.createElement(Text, { color: theme.dim },
                    React.createElement(Spinner, { type: "dots" }),
                    " Loading models\u2026")
                    : models.length ? React.createElement(SelectInput, { limit: 4, items: models.map(model => ({ label: model, value: model })), onSelect: item => { setStatus(previous => ({ ...previous, model: item.value })); setModels(null); } })
                        : React.createElement(Text, null, "No installed/configured models found. Use /connect or /model provider/model-id.")),
            modePicker && React.createElement(React.Fragment, null,
                React.createElement(Text, { color: theme.brand }, "Choose mode \u00B7 Esc closes"),
                React.createElement(SelectInput, { items: ['standard', 'cautious', 'read-only'].map(mode => ({ label: mode, value: mode })), onSelect: item => {
                        setStatus(previous => ({ ...previous, mode: item.value }));
                        setModePicker(false);
                        add('system', 'Mode set to ' + item.value + '.');
                    } })),
            keyProvider && React.createElement(React.Fragment, null,
                React.createElement(Text, { color: theme.brand },
                    "Connect ",
                    keyProvider,
                    " \u00B7 system keyring \u00B7 Esc cancels"),
                React.createElement(Text, { color: theme.dim }, "Paste your API key. It is not sent as a chat message."),
                React.createElement(TextInput, { mask: "\u2022", value: keyDraft, onChange: setKeyDraft, onSubmit: key => {
                        client.current?.send({ command: 'connect', provider: keyProvider, key });
                        setKeyDraft('');
                        setKeyProvider('');
                    } }))) : null,
        React.createElement(Box, { display: modal ? 'none' : 'flex', height: modal ? 0 : 8, flexDirection: "column" },
            React.createElement(InputBar, { onSubmit: submitDraft, busy: busy, attachmentLabel: attachmentLabel, onDraftChange: value => { if (value.trim() && !value.trim().startsWith('/'))
                    attachmentDraft.current = value; }, disabled: !online || modal || !commands.length || exiting, slashCommands: commands, insertion: insertion, modelLabel: status.model, modeLabel: status.mode + (status.localImages ? ' · images local-only' : ''), onMenuChange: setCommandMenu, history: promptHistory })),
        statusbar ? React.createElement(StatusLine, { busy: busy, workers: activeWorkers, tokens: (status.inputTokens || 0) + (status.outputTokens || 0), scrolled: offset > 0 }) : React.createElement(Box, { height: 1 }));
}
//# sourceMappingURL=App.js.map