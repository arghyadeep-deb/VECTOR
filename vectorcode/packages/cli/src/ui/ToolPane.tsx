/**
 * ToolPane — right side panel showing tool execution timeline + active sessions.
 */

import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { theme, glyphs } from './theme.js';
import type { ToolEvent } from '../types.js';

interface ToolPaneProps {
  events: ToolEvent[];
  width?: number;
}

export const ToolPane: React.FC<ToolPaneProps> = ({ events, width = 40 }) => {
  return (
    <Box flexDirection="column" width={width} paddingX={1} borderStyle="single" borderColor={theme.dim}>
      {/* Header */}
      <Box>
        <Text color={theme.accent} bold>
          Tool Activity
        </Text>
        <Box flexGrow={1} justifyContent="flex-end">
          <Text color={theme.dim}>{events.length}</Text>
        </Box>
      </Box>

      {/* Events (newest first, capped at 12) */}
      <Box flexDirection="column" marginTop={1}>
        {events.length === 0 && (
          <Text color={theme.dim} italic>
            no tools called yet
          </Text>
        )}
        {events
          .slice(-12)
          .reverse()
          .map((e) => (
            <ToolRow key={e.id} event={e} />
          ))}
      </Box>
    </Box>
  );
};

const ToolRow: React.FC<{ event: ToolEvent }> = ({ event }) => {
  const { name, status, startedAt, finishedAt, preview, error } = event;
  const dur = finishedAt ? finishedAt - startedAt : Date.now() - startedAt;

  const marker =
    status === 'done' ? glyphs.toolDone : status === 'failed' ? glyphs.toolFail : glyphs.toolStart;
  const color =
    status === 'done' ? theme.success : status === 'failed' ? theme.error : theme.accent;

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={color}>{marker} </Text>
        <Text color={theme.brandText}>{name}</Text>
        <Box flexGrow={1} justifyContent="flex-end">
          {status === 'running' ? (
            <Text color={theme.dim}>
              <Spinner type="dots" />
            </Text>
          ) : (
            <Text color={theme.dim}>{dur}ms</Text>
          )}
        </Box>
      </Box>
      {(preview || error) && (
        <Box marginLeft={2}>
          <Text color={error ? theme.error : theme.dim}>
            {(error || preview || '').slice(0, 40)}
          </Text>
        </Box>
      )}
    </Box>
  );
};
