/**
 * Welcome banner — VectorCode ⟨▶⟩ mark, version, tips.
 * Mirrors the Python CLI banner aesthetic.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme, glyphs } from './theme.js';

interface BannerProps {
  version?: string;
  model?: string;
  modelsOnline?: number;
  hasVectorMd?: boolean;
}

export const Banner: React.FC<BannerProps> = ({
  version = '0.1.0',
  model = 'vector-focus',
  modelsOnline = 0,
  hasVectorMd = false,
}) => {
  return (
    <Box flexDirection="column" paddingY={1} paddingX={2}>
      {/* Title row: ⟨▶⟩ VectorCode <pad> v0.1.0 */}
      <Box>
        <Text color={theme.brand} bold>
          {glyphs.mark}{' '}
        </Text>
        <Text color={theme.brandText} bold>
          VectorCode
        </Text>
        <Text color={theme.dim}> · autonomous coding agent · </Text>
        <Text color={theme.dim}>v{version}</Text>
      </Box>

      {/* Separator */}
      <Box marginTop={1}>
        <Text color={theme.accent}>{glyphs.horizontal.repeat(60)}</Text>
      </Box>

      {/* Status block */}
      <Box flexDirection="column" marginTop={1}>
        <Box>
          <Text color={theme.accent}>Model </Text>
          <Text>    </Text>
          <Text color={theme.brandText} bold>
            {model}
          </Text>
        </Box>
        <Box>
          <Text color={theme.accent}>Status</Text>
          <Text>    </Text>
          {modelsOnline > 0 ? (
            <>
              <Text color={theme.success}>{glyphs.online} </Text>
              <Text>online </Text>
              <Text color={theme.dim}>
                · {modelsOnline} models · ready
              </Text>
            </>
          ) : (
            <>
              <Text color={theme.warning}>{glyphs.offline} </Text>
              <Text color={theme.dim}>offline</Text>
            </>
          )}
        </Box>
      </Box>

      {/* Separator */}
      <Box marginTop={1}>
        <Text color={theme.accent}>{glyphs.horizontal.repeat(60)}</Text>
      </Box>

      {/* Quick actions */}
      <Box flexDirection="column" marginTop={1}>
        <ActionRow cmd="/help" desc="list all commands" />
        <ActionRow cmd="@<file>" desc="attach files to context" />
        <ActionRow cmd="/sparc <task>" desc="run SPARC pipeline" />
        <ActionRow cmd="Ctrl+C" desc="cancel · /quit to exit" />
      </Box>

      {/* VECTOR.md status */}
      <Box marginTop={1}>
        {hasVectorMd ? (
          <>
            <Text color={theme.success}>{glyphs.online} </Text>
            <Text color={theme.dim}>VECTOR.md loaded</Text>
          </>
        ) : (
          <>
            <Text color={theme.warning}>{glyphs.offline} </Text>
            <Text color={theme.dim}>
              No VECTOR.md · run{' '}
            </Text>
            <Text color={theme.accent}>/init</Text>
            <Text color={theme.dim}> to create one</Text>
          </>
        )}
      </Box>
    </Box>
  );
};

const ActionRow: React.FC<{ cmd: string; desc: string }> = ({ cmd, desc }) => (
  <Box>
    <Text color={theme.accent}>{cmd.padEnd(18)}</Text>
    <Text color={theme.dim}>{desc}</Text>
  </Box>
);
