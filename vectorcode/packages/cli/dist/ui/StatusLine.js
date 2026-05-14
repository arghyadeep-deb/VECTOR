/**
 * StatusLine — bottom thin bar showing iteration usage, hints, hotkeys.
 */
import React from 'react';
import { Box, Text } from 'ink';
import { theme } from './theme.js';
export const StatusLine = ({ iterationsUsed = 0, iterationsMax = 90, hint = 'Tab toggle pane · Ctrl+C cancel · /quit exit', busy = false, }) => {
    const pct = iterationsMax > 0 ? Math.round((iterationsUsed / iterationsMax) * 100) : 0;
    const barWidth = 10;
    const filled = Math.round((pct / 100) * barWidth);
    const bar = '█'.repeat(filled) + '░'.repeat(barWidth - filled);
    return (React.createElement(Box, { paddingX: 1 },
        busy && (React.createElement(React.Fragment, null,
            React.createElement(Text, { color: theme.warning }, "\u25CF "),
            React.createElement(Text, { color: theme.dim }, "working \u00B7 "))),
        React.createElement(Text, { color: theme.dim }, "iter "),
        React.createElement(Text, { color: pct > 80 ? theme.warning : theme.accent },
            iterationsUsed,
            "/",
            iterationsMax),
        React.createElement(Text, { color: theme.dim }, " ["),
        React.createElement(Text, { color: pct > 80 ? theme.warning : theme.success }, bar),
        React.createElement(Text, { color: theme.dim }, "]"),
        React.createElement(Box, { flexGrow: 1, justifyContent: "flex-end" },
            React.createElement(Text, { color: theme.dim }, hint))));
};
//# sourceMappingURL=StatusLine.js.map