import React from 'react';
import { Box, Text } from 'ink';
import { theme } from './theme.js';
export function Banner({ cwd = process.cwd(), model = 'vector-focus', height = 15 }) {
    if (height < 6)
        return React.createElement(Box, { height: height });
    return React.createElement(Box, { height: height, flexDirection: "column", alignItems: "center", justifyContent: "center", overflow: "hidden" },
        React.createElement(Box, { height: 1, flexShrink: 0 },
            React.createElement(Text, { color: theme.brand, bold: true }, "\u25C6  V E C T O R C O D E")),
        React.createElement(Box, { height: 1, flexShrink: 0 },
            React.createElement(Text, { color: theme.dim }, "Your project. Your model. Your next move.")),
        React.createElement(Box, { height: 1, flexShrink: 0, marginTop: 1 },
            React.createElement(Text, { color: theme.brandText }, cwd.split(/[\\/]/).pop())),
        React.createElement(Box, { height: 1, flexShrink: 0 },
            React.createElement(Text, { color: theme.dim }, model)),
        height > 11 && React.createElement(Box, { marginTop: 1, flexDirection: "column" },
            React.createElement(Text, { color: theme.dim }, "Ask a question, inspect a file, or work through a change."),
            React.createElement(Text, { color: theme.dim }, "/models choose model    /connect add key    /help commands")));
}
//# sourceMappingURL=Banner.js.map