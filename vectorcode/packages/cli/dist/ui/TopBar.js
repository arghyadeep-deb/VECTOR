/**
 * TopBar — persistent header showing model, mode, gateway health, token usage.
 */
import React from 'react';
import { Box, Text } from 'ink';
import { theme, glyphs } from './theme.js';
export const TopBar = ({ status, gatewayHealthy }) => {
    const model = status.model ?? 'unknown';
    const mode = status.mode ?? 'standard';
    const tokens = (status.inputTokens ?? 0) + (status.outputTokens ?? 0);
    const cost = status.costUsd ?? 0;
    return (React.createElement(Box, { paddingX: 1 },
        React.createElement(Text, { color: theme.brand, bold: true }, glyphs.mark),
        React.createElement(Text, null, " "),
        React.createElement(Text, { color: theme.brandText, bold: true }, "VectorCode"),
        React.createElement(Text, { color: theme.dim }, " \u00B7 "),
        React.createElement(Text, { color: theme.accent }, model),
        React.createElement(Text, { color: theme.dim }, " \u00B7 "),
        React.createElement(Text, { color: theme.active }, mode),
        React.createElement(Text, { color: theme.dim }, " \u00B7 "),
        gatewayHealthy ? (React.createElement(React.Fragment, null,
            React.createElement(Text, { color: theme.success }, glyphs.online),
            React.createElement(Text, { color: theme.dim }, " gateway"))) : (React.createElement(React.Fragment, null,
            React.createElement(Text, { color: theme.error }, glyphs.offline),
            React.createElement(Text, { color: theme.dim }, " gateway down"))),
        React.createElement(Box, { flexGrow: 1, justifyContent: "flex-end" },
            React.createElement(Text, { color: theme.dim },
                tokens.toLocaleString(),
                " tokens \u00B7 $",
                cost.toFixed(4)))));
};
//# sourceMappingURL=TopBar.js.map