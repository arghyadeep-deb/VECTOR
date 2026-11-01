import React from 'react';
import { Box, Text } from 'ink';
import { theme } from './theme.js';
export function StatusLine({ busy = false, tokens = 0, scrolled = false, workers = 0 }) {
    return React.createElement(Box, { height: 1, paddingX: 2, justifyContent: "space-between", overflow: "hidden" },
        React.createElement(Text, { color: theme.dim }, workers > 0 ? `${workers} worker${workers === 1 ? '' : 's'} · /workers · Esc stop` :
            busy ? 'Esc stop after current operation' : 'Enter send · Alt+Enter newline · Tab activity'),
        React.createElement(Text, { color: theme.dim }, scrolled ? 'PgDn return to latest' : `${tokens.toLocaleString()} tokens`));
}
//# sourceMappingURL=StatusLine.js.map