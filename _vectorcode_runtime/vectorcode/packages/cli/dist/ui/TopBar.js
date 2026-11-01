import React from 'react';
import { Box, Text } from 'ink';
import { theme } from './theme.js';
export function TopBar({ status, gatewayHealthy }) {
    return React.createElement(Box, { height: 2, paddingX: 2, justifyContent: "space-between", overflow: "hidden" },
        React.createElement(Text, { color: theme.brand, bold: true }, "\u25C6 VECTORCODE"),
        React.createElement(Text, { color: theme.dim, wrap: "truncate-middle" }, status.title || process.cwd().split(/[\\/]/).pop()),
        React.createElement(Text, { color: gatewayHealthy ? theme.success : theme.warning }, gatewayHealthy ? '● local engine' : '○ engine unavailable'));
}
//# sourceMappingURL=TopBar.js.map