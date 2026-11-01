import React, { useMemo } from 'react';
import { Box, Text } from 'ink';
import { transcriptLines, viewport } from './transcript.js';
export function ChatPane({ messages, width, height, offset = 0 }) {
    const lines = useMemo(() => transcriptLines(messages, width - 4), [messages, width]);
    return React.createElement(Box, { width: width, height: height, paddingX: 2, flexDirection: "column", overflow: "hidden" }, viewport(lines, height, offset).map((line, index) => React.createElement(Text, { key: index, wrap: "truncate-end" }, line || ' ')));
}
//# sourceMappingURL=ChatPane.js.map