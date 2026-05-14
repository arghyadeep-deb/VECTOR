/**
 * ChatPane — main conversation view.
 * Renders user/assistant/tool messages with smooth streaming + colors.
 */

import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { theme, glyphs } from './theme.js';
import type { ChatMessage } from '../types.js';

interface ChatPaneProps {
  messages: ChatMessage[];
  thinking?: boolean;
  thinkingText?: string;
}

export const ChatPane: React.FC<ChatPaneProps> = ({
  messages,
  thinking = false,
  thinkingText = 'thinking',
}) => {
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      {messages.map((m) => (
        <MessageView key={m.id} message={m} />
      ))}
      {thinking && (
        <Box marginTop={1}>
          <Text color={theme.dim}>
            <Spinner type="dots" />
          </Text>
          <Text color={theme.dim}> {thinkingText}...</Text>
        </Box>
      )}
    </Box>
  );
};

const MessageView: React.FC<{ message: ChatMessage }> = ({ message }) => {
  if (message.role === 'user') {
    return (
      <Box marginTop={1}>
        <Text color={theme.user} bold>
          {glyphs.prompt}{' '}
        </Text>
        <Text color={theme.brandText}>{message.content}</Text>
      </Box>
    );
  }

  if (message.role === 'assistant') {
    return (
      <Box marginTop={1} flexDirection="column">
        <Text color={theme.assistant}>{message.content}</Text>
        {message.streaming && (
          <Text color={theme.dim}>
            <Spinner type="line" />
          </Text>
        )}
      </Box>
    );
  }

  if (message.role === 'tool') {
    return <ToolMessage message={message} />;
  }

  // system
  return (
    <Box marginTop={1}>
      <Text color={theme.dim} italic>
        {message.content}
      </Text>
    </Box>
  );
};

const ToolMessage: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const status = message.toolStatus ?? 'running';
  const name = message.toolName ?? 'unknown';
  const argsPreview = message.toolArgs
    ? Object.entries(message.toolArgs)
        .slice(0, 2)
        .map(([k, v]) => `${k}=${typeof v === 'string' ? v.slice(0, 40) : JSON.stringify(v).slice(0, 40)}`)
        .join(', ')
    : '';

  const marker =
    status === 'done'
      ? glyphs.toolDone
      : status === 'failed'
      ? glyphs.toolFail
      : glyphs.toolStart;

  const markerColor =
    status === 'done'
      ? theme.success
      : status === 'failed'
      ? theme.error
      : theme.accent;

  return (
    <Box marginTop={1} flexDirection="column">
      {/* First line: marker tool(args) */}
      <Box>
        <Text color={markerColor}>{marker} </Text>
        <Text color={theme.brandText} bold>
          {name}
        </Text>
        {argsPreview && (
          <Text color={theme.dim}>({argsPreview})</Text>
        )}
        {status === 'running' && (
          <>
            <Text> </Text>
            <Text color={theme.dim}>
              <Spinner type="dots" />
            </Text>
          </>
        )}
      </Box>

      {/* Result line if available */}
      {message.content && status !== 'running' && (
        <Box marginLeft={2}>
          <Text color={theme.dim}>
            {message.content.slice(0, 200)}
            {message.toolDurationMs !== undefined &&
              ` · ${message.toolDurationMs}ms`}
          </Text>
        </Box>
      )}
    </Box>
  );
};
