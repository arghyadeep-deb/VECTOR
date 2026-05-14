/**
 * Reactor — small circular arc reactor symbol (no text inside).
 * 5 rows × ~12 cols. Concentric rings with glowing core dot.
 */

import React from 'react';
import { Box, Text } from 'ink';

export const Reactor: React.FC = () => (
  <Box flexDirection="column">
    <Box>
      <Text color="cyan">    ╭─────╮</Text>
    </Box>
    <Box>
      <Text color="cyan">   ╱ </Text>
      <Text color="cyanBright">╭───╮</Text>
      <Text color="cyan"> ╲</Text>
    </Box>
    <Box>
      <Text color="cyan">  │ </Text>
      <Text color="cyanBright">│  </Text>
      <Text color="whiteBright" bold>◉</Text>
      <Text color="cyanBright">  │</Text>
      <Text color="cyan"> │</Text>
    </Box>
    <Box>
      <Text color="cyan">   ╲ </Text>
      <Text color="cyanBright">╰───╯</Text>
      <Text color="cyan"> ╱</Text>
    </Box>
    <Box>
      <Text color="cyan">    ╰─────╯</Text>
    </Box>
  </Box>
);
