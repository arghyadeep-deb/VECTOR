/**
 * Reactor — small circular arc reactor symbol (no text inside).
 * 5 rows × ~12 cols. Concentric rings with glowing core dot.
 */
import React from 'react';
import { Box, Text } from 'ink';
export const Reactor = () => (React.createElement(Box, { flexDirection: "column" },
    React.createElement(Box, null,
        React.createElement(Text, { color: "cyan" }, "    \u256D\u2500\u2500\u2500\u2500\u2500\u256E")),
    React.createElement(Box, null,
        React.createElement(Text, { color: "cyan" }, "   \u2571 "),
        React.createElement(Text, { color: "cyanBright" }, "\u256D\u2500\u2500\u2500\u256E"),
        React.createElement(Text, { color: "cyan" }, " \u2572")),
    React.createElement(Box, null,
        React.createElement(Text, { color: "cyan" }, "  \u2502 "),
        React.createElement(Text, { color: "cyanBright" }, "\u2502  "),
        React.createElement(Text, { color: "whiteBright", bold: true }, "\u25C9"),
        React.createElement(Text, { color: "cyanBright" }, "  \u2502"),
        React.createElement(Text, { color: "cyan" }, " \u2502")),
    React.createElement(Box, null,
        React.createElement(Text, { color: "cyan" }, "   \u2572 "),
        React.createElement(Text, { color: "cyanBright" }, "\u2570\u2500\u2500\u2500\u256F"),
        React.createElement(Text, { color: "cyan" }, " \u2571")),
    React.createElement(Box, null,
        React.createElement(Text, { color: "cyan" }, "    \u2570\u2500\u2500\u2500\u2500\u2500\u256F"))));
//# sourceMappingURL=Reactor.js.map