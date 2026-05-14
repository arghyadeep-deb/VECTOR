/**
 * Banner — minimal welcome line, Claude Code style.
 * Just one symbol + name + tip. No frames, no reactor, no animation.
 */
import React from 'react';
import { Box, Text } from 'ink';
export const Banner = ({ cwd = process.cwd() }) => {
    const home = process.env.HOME || process.env.USERPROFILE || '';
    let displayCwd = home && cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;
    if (displayCwd.length > 60)
        displayCwd = '...' + displayCwd.slice(-57);
    return (React.createElement(Box, { flexDirection: "column", paddingY: 1 },
        React.createElement(Box, null,
            React.createElement(Text, { color: "cyan" }, "\u25B8 "),
            React.createElement(Text, { color: "whiteBright", bold: true }, "VectorCode"),
            React.createElement(Text, { dimColor: true }, '  /help for commands · @file to attach · /quit to exit')),
        React.createElement(Box, null,
            React.createElement(Text, { dimColor: true }, `     cwd: ${displayCwd}`))));
};
//# sourceMappingURL=Banner.js.map