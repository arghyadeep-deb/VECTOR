/**
 * Welcome banner — JARVIS arc reactor with VECTOR core + status block.
 */
import React from 'react';
import { Box, Text } from 'ink';
import { theme, glyphs } from './theme.js';
import { ArcReactor } from './ArcReactor.js';
export const Banner = ({ version = '0.1.0', model = 'vector-focus', modelsOnline = 0, hasVectorMd = false, }) => {
    return (React.createElement(Box, { flexDirection: "column", paddingY: 1, paddingX: 2 },
        React.createElement(Box, null,
            React.createElement(ArcReactor, { size: "medium" }),
            React.createElement(Box, { flexDirection: "column", marginLeft: 2, paddingTop: 1 },
                React.createElement(Box, null,
                    React.createElement(Text, { color: theme.brandText, bold: true }, "VectorCode"),
                    React.createElement(Text, { color: theme.dim },
                        "  v",
                        version)),
                React.createElement(Box, null,
                    React.createElement(Text, { color: theme.dim, italic: true }, "autonomous coding agent")),
                React.createElement(Box, { marginTop: 1 },
                    React.createElement(Text, { color: theme.accent }, glyphs.horizontal.repeat(34))),
                React.createElement(Box, null,
                    React.createElement(Text, { color: theme.accent }, "Model "),
                    React.createElement(Text, null, "    "),
                    React.createElement(Text, { color: theme.brandText, bold: true }, model)),
                React.createElement(Box, null,
                    React.createElement(Text, { color: theme.accent }, "Status"),
                    React.createElement(Text, null, "    "),
                    modelsOnline > 0 ? (React.createElement(React.Fragment, null,
                        React.createElement(Text, { color: theme.success },
                            glyphs.online,
                            " "),
                        React.createElement(Text, null, "online "),
                        React.createElement(Text, { color: theme.dim },
                            "\u00B7 ",
                            modelsOnline,
                            " models \u00B7 ready"))) : (React.createElement(React.Fragment, null,
                        React.createElement(Text, { color: theme.warning },
                            glyphs.offline,
                            " "),
                        React.createElement(Text, { color: theme.dim }, "offline")))),
                React.createElement(Box, null, hasVectorMd ? (React.createElement(React.Fragment, null,
                    React.createElement(Text, { color: theme.success },
                        glyphs.online,
                        " "),
                    React.createElement(Text, { color: theme.dim }, "VECTOR.md loaded"))) : (React.createElement(React.Fragment, null,
                    React.createElement(Text, { color: theme.warning },
                        glyphs.offline,
                        " "),
                    React.createElement(Text, { color: theme.dim }, "No VECTOR.md \u00B7 "),
                    React.createElement(Text, { color: theme.accent }, "/init")))),
                React.createElement(Box, { marginTop: 1 },
                    React.createElement(Text, { color: theme.accent }, glyphs.horizontal.repeat(34))))),
        React.createElement(Box, { flexDirection: "column", marginTop: 1 },
            React.createElement(ActionRow, { cmd: "/help", desc: "list all commands" }),
            React.createElement(ActionRow, { cmd: "@<file>", desc: "attach files to context" }),
            React.createElement(ActionRow, { cmd: "/sparc <task>", desc: "run SPARC pipeline" }),
            React.createElement(ActionRow, { cmd: "Ctrl+C", desc: "cancel \u00B7 /quit to exit" }))));
};
const ActionRow = ({ cmd, desc }) => (React.createElement(Box, null,
    React.createElement(Text, { color: theme.accent }, cmd.padEnd(18)),
    React.createElement(Text, { color: theme.dim }, desc)));
//# sourceMappingURL=Banner.js.map