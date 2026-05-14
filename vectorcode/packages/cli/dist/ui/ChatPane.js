/**
 * ChatPane — main conversation view.
 * Renders user/assistant/tool messages with smooth streaming + colors.
 */
import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { theme, glyphs } from './theme.js';
export const ChatPane = ({ messages, thinking = false, thinkingText = 'thinking', }) => {
    return (React.createElement(Box, { flexDirection: "column", flexGrow: 1, paddingX: 1 },
        messages.map((m) => (React.createElement(MessageView, { key: m.id, message: m }))),
        thinking && (React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.dim },
                React.createElement(Spinner, { type: "dots" })),
            React.createElement(Text, { color: theme.dim },
                " ",
                thinkingText,
                "...")))));
};
const MessageView = ({ message }) => {
    if (message.role === 'user') {
        return (React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.user, bold: true },
                glyphs.prompt,
                ' '),
            React.createElement(Text, { color: theme.brandText }, message.content)));
    }
    if (message.role === 'assistant') {
        return (React.createElement(Box, { marginTop: 1, flexDirection: "column" },
            React.createElement(Text, { color: theme.assistant }, message.content),
            message.streaming && (React.createElement(Text, { color: theme.dim },
                React.createElement(Spinner, { type: "line" })))));
    }
    if (message.role === 'tool') {
        return React.createElement(ToolMessage, { message: message });
    }
    // system
    return (React.createElement(Box, { marginTop: 1 },
        React.createElement(Text, { color: theme.dim, italic: true }, message.content)));
};
const ToolMessage = ({ message }) => {
    const status = message.toolStatus ?? 'running';
    const name = message.toolName ?? 'unknown';
    const argsPreview = message.toolArgs
        ? Object.entries(message.toolArgs)
            .slice(0, 2)
            .map(([k, v]) => `${k}=${typeof v === 'string' ? v.slice(0, 40) : JSON.stringify(v).slice(0, 40)}`)
            .join(', ')
        : '';
    const marker = status === 'done'
        ? glyphs.toolDone
        : status === 'failed'
            ? glyphs.toolFail
            : glyphs.toolStart;
    const markerColor = status === 'done'
        ? theme.success
        : status === 'failed'
            ? theme.error
            : theme.accent;
    return (React.createElement(Box, { marginTop: 1, flexDirection: "column" },
        React.createElement(Box, null,
            React.createElement(Text, { color: markerColor },
                marker,
                " "),
            React.createElement(Text, { color: theme.brandText, bold: true }, name),
            argsPreview && (React.createElement(Text, { color: theme.dim },
                "(",
                argsPreview,
                ")")),
            status === 'running' && (React.createElement(React.Fragment, null,
                React.createElement(Text, null, " "),
                React.createElement(Text, { color: theme.dim },
                    React.createElement(Spinner, { type: "dots" }))))),
        message.content && status !== 'running' && (React.createElement(Box, { marginLeft: 2 },
            React.createElement(Text, { color: theme.dim },
                message.content.slice(0, 200),
                message.toolDurationMs !== undefined &&
                    ` · ${message.toolDurationMs}ms`)))));
};
//# sourceMappingURL=ChatPane.js.map