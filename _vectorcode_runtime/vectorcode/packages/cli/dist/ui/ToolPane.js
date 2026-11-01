/**
 * ToolPane — right side panel showing tool execution timeline + active sessions.
 */
import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { theme, glyphs } from './theme.js';
export const ToolPane = ({ events, width = 40 }) => {
    return (React.createElement(Box, { flexDirection: "column", width: width, paddingX: 1, borderStyle: "single", borderColor: theme.dim },
        React.createElement(Box, null,
            React.createElement(Text, { color: theme.accent, bold: true }, "Tool Activity"),
            React.createElement(Box, { flexGrow: 1, justifyContent: "flex-end" },
                React.createElement(Text, { color: theme.dim }, events.length))),
        React.createElement(Box, { flexDirection: "column", marginTop: 1 },
            events.length === 0 && (React.createElement(Text, { color: theme.dim, italic: true }, "no tools called yet")),
            events
                .slice(-12)
                .reverse()
                .map((e) => (React.createElement(ToolRow, { key: e.id, event: e }))))));
};
const ToolRow = ({ event }) => {
    const { name, status, startedAt, finishedAt, preview, error } = event;
    const dur = finishedAt ? finishedAt - startedAt : Date.now() - startedAt;
    const marker = status === 'done' ? glyphs.toolDone : status === 'failed' ? glyphs.toolFail : glyphs.toolStart;
    const color = status === 'done' ? theme.success : status === 'failed' ? theme.error : theme.accent;
    return (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Box, null,
            React.createElement(Text, { color: color },
                marker,
                " "),
            React.createElement(Text, { color: theme.brandText }, name),
            React.createElement(Box, { flexGrow: 1, justifyContent: "flex-end" }, status === 'running' ? (React.createElement(Text, { color: theme.dim },
                React.createElement(Spinner, { type: "dots" }))) : (React.createElement(Text, { color: theme.dim },
                dur,
                "ms")))),
        (preview || error) && (React.createElement(Box, { marginLeft: 2 },
            React.createElement(Text, { color: error ? theme.error : theme.dim }, (error || preview || '').slice(0, 40))))));
};
//# sourceMappingURL=ToolPane.js.map