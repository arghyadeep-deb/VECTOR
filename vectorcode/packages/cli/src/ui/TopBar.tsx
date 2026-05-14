/**
 * TopBar — persistent header showing model, mode, gateway health, token usage.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme, glyphs } from './theme.js';
import type { SessionStatus } from '../types.js';

interface TopBarProps {
  status: Partial<SessionStatus>;
  gatewayHealthy: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({ status, gatewayHealthy }) => {
  const model = status.model ?? 'unknown';
  const mode = status.mode ?? 'standard';
  const tokens = (status.inputTokens ?? 0) + (status.outputTokens ?? 0);
  const cost = status.costUsd ?? 0;

  return (
    <Box paddingX={1}>
      {/* Logo + brand */}
      <Text color={theme.brand} bold>
        {glyphs.mark}
      </Text>
      <Text> </Text>
      <Text color={theme.brandText} bold>
        VectorCode
      </Text>

      {/* Separator */}
      <Text color={theme.dim}> · </Text>

      {/* Model */}
      <Text color={theme.accent}>{model}</Text>

      <Text color={theme.dim}> · </Text>

      {/* Mode */}
      <Text color={theme.active}>{mode}</Text>

      <Text color={theme.dim}> · </Text>

      {/* Gateway health */}
      {gatewayHealthy ? (
        <>
          <Text color={theme.success}>{glyphs.online}</Text>
          <Text color={theme.dim}> gateway</Text>
        </>
      ) : (
        <>
          <Text color={theme.error}>{glyphs.offline}</Text>
          <Text color={theme.dim}> gateway down</Text>
        </>
      )}

      {/* Token usage (right-side) */}
      <Box flexGrow={1} justifyContent="flex-end">
        <Text color={theme.dim}>
          {tokens.toLocaleString()} tokens · ${cost.toFixed(4)}
        </Text>
      </Box>
    </Box>
  );
};
