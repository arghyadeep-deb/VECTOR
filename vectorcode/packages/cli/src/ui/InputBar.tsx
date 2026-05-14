/**
 * InputBar — user input with slash command autocomplete.
 */

import React, { useState, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { theme, glyphs } from './theme.js';
import type { SlashCommand } from '../types.js';

interface InputBarProps {
  onSubmit: (value: string) => void;
  onCancel?: () => void;
  busy?: boolean;
  placeholder?: string;
  slashCommands: SlashCommand[];
  modelLabel?: string;
  modeLabel?: string;
}

export const InputBar: React.FC<InputBarProps> = ({
  onSubmit,
  onCancel,
  busy = false,
  placeholder = 'Type a task or /help',
  slashCommands,
  modelLabel = 'vector',
  modeLabel = 'repl',
}) => {
  const [value, setValue] = useState('');

  // Slash autocomplete suggestions
  const suggestions = useMemo(() => {
    if (!value.startsWith('/')) return [];
    const q = value.slice(1).toLowerCase();
    return slashCommands
      .filter((c) => c.name.toLowerCase().startsWith(q))
      .slice(0, 6);
  }, [value, slashCommands]);

  useInput((input, key) => {
    if (key.escape && onCancel) {
      onCancel();
    }
  });

  const handleSubmit = (v: string) => {
    if (!v.trim() || busy) return;
    onSubmit(v.trim());
    setValue('');
  };

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Slash command suggestions (above input) */}
      {suggestions.length > 0 && (
        <Box flexDirection="column" marginBottom={1}>
          {suggestions.map((c) => (
            <Box key={c.name}>
              <Text color={theme.accent}>{('/' + c.name).padEnd(20)}</Text>
              <Text color={theme.dim}>{c.description}</Text>
            </Box>
          ))}
        </Box>
      )}

      {/* Context line: dim mode·model */}
      <Box>
        <Text color={theme.dim}>
          {modeLabel} · {modelLabel}
        </Text>
      </Box>

      {/* Prompt line: > input */}
      <Box>
        <Text color={theme.brand} bold>
          {glyphs.prompt}{' '}
        </Text>
        {busy ? (
          <Text color={theme.dim}>{value || placeholder}</Text>
        ) : (
          <TextInput
            value={value}
            onChange={setValue}
            onSubmit={handleSubmit}
            placeholder={placeholder}
          />
        )}
      </Box>
    </Box>
  );
};
