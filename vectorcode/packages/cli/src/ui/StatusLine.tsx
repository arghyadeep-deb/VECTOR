/**
 * StatusLine — bottom thin bar showing iteration usage, hints, hotkeys.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme } from './theme.js';

interface StatusLineProps {
  iterationsUsed?: number;
  iterationsMax?: number;
  hint?: string;
  busy?: boolean;
}

export const StatusLine: React.FC<StatusLineProps> = ({
  iterationsUsed = 0,
  iterationsMax = 90,
  hint = 'Tab toggle pane · Ctrl+C cancel · /quit exit',
  busy = false,
}) => {
  const pct = iterationsMax > 0 ? Math.round((iterationsUsed / iterationsMax) * 100) : 0;
  const barWidth = 10;
  const filled = Math.round((pct / 100) * barWidth);
  const bar = '█'.repeat(filled) + '░'.repeat(barWidth - filled);

  return (
    <Box paddingX={1}>
      {busy && (
        <>
          <Text color={theme.warning}>● </Text>
          <Text color={theme.dim}>working · </Text>
        </>
      )}
      <Text color={theme.dim}>iter </Text>
      <Text color={pct > 80 ? theme.warning : theme.accent}>
        {iterationsUsed}/{iterationsMax}
      </Text>
      <Text color={theme.dim}> [</Text>
      <Text color={pct > 80 ? theme.warning : theme.success}>{bar}</Text>
      <Text color={theme.dim}>]</Text>

      <Box flexGrow={1} justifyContent="flex-end">
        <Text color={theme.dim}>{hint}</Text>
      </Box>
    </Box>
  );
};
