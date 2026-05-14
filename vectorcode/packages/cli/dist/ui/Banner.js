/**
 * Banner — circular reactor + status panel, Claude Code style.
 */
import React from 'react';
import { Box, Text } from 'ink';
import { Reactor } from './Reactor.js';
export const Banner = ({ cwd = process.cwd(), model = 'vector-focus', modelsOnline = 0, }) => {
    const home = process.env.HOME || process.env.USERPROFILE || '';
    let displayCwd = home && cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;
    if (displayCwd.length > 60)
        displayCwd = '...' + displayCwd.slice(-57);
    return (React.createElement(Box, { flexDirection: "column", paddingY: 1 },
        React.createElement(Box, null,
            React.createElement(Reactor, null),
            React.createElement(Box, { flexDirection: "column", marginLeft: 4 },
                React.createElement(Box, null,
                    React.createElement(Text, { color: "whiteBright", bold: true }, "VectorCode"),
                    React.createElement(Text, { dimColor: true }, "  v0.1.0")),
                React.createElement(Box, null,
                    React.createElement(Text, { dimColor: true }, "autonomous coding agent")),
                React.createElement(Box, null, " "),
                React.createElement(Box, null,
                    React.createElement(Text, { color: "cyan" }, "model"),
                    React.createElement(Text, null, "  "),
                    React.createElement(Text, { color: "whiteBright", bold: true }, model),
                    React.createElement(Text, { dimColor: true }, "  \u00B7  "),
                    modelsOnline > 0 ? (React.createElement(React.Fragment, null,
                        React.createElement(Text, { color: "green" }, "\u25CF online"),
                        React.createElement(Text, { dimColor: true }, "  \u00B7  "),
                        React.createElement(Text, { color: "whiteBright", bold: true }, modelsOnline),
                        React.createElement(Text, { dimColor: true }, " models"))) : (React.createElement(Text, { color: "yellow" }, "\u25CB offline"))),
                React.createElement(Box, null,
                    React.createElement(Text, { dimColor: true }, `cwd:   ${displayCwd}`)))),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { dimColor: true },
                "/help for commands  \u00B7  @file to attach  \u00B7  /sparc ",
                '<task>',
                "  \u00B7  /quit to exit"))));
};
//# sourceMappingURL=Banner.js.map