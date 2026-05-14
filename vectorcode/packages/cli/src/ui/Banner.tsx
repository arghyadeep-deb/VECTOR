/**
 * Banner — minimal welcome line, Claude Code style.
 * Just one symbol + name + tip. No frames, no reactor, no animation.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface BannerProps {
  cwd?: string;
}

export const Banner: React.FC<BannerProps> = ({ cwd = process.cwd() }) => {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  let displayCwd = home && cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;
  if (displayCwd.length > 60) displayCwd = '...' + displayCwd.slice(-57);

  return (
    <Box flexDirection="column" paddingY={1}>
      <Box>
        <Text color="cyan">▸ </Text>
        <Text color="whiteBright" bold>
          VectorCode
        </Text>
        <Text dimColor>
          {'  /help for commands · @file to attach · /quit to exit'}
        </Text>
      </Box>
      <Box>
        <Text dimColor>{`     cwd: ${displayCwd}`}</Text>
      </Box>
    </Box>
  );
};
