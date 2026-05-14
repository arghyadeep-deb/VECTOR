/**
 * Banner — circular reactor + status panel, Claude Code style.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { Reactor } from './Reactor.js';

interface BannerProps {
  cwd?: string;
  model?: string;
  modelsOnline?: number;
}

export const Banner: React.FC<BannerProps> = ({
  cwd = process.cwd(),
  model = 'vector-focus',
  modelsOnline = 0,
}) => {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  let displayCwd = home && cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;
  if (displayCwd.length > 60) displayCwd = '...' + displayCwd.slice(-57);

  return (
    <Box flexDirection="column" paddingY={1}>
      <Box>
        {/* Left: reactor */}
        <Reactor />

        {/* Right: status panel (5 lines aligned with reactor) */}
        <Box flexDirection="column" marginLeft={4}>
          <Box>
            <Text color="whiteBright" bold>VectorCode</Text>
            <Text dimColor>  v0.1.0</Text>
          </Box>
          <Box>
            <Text dimColor>autonomous coding agent</Text>
          </Box>
          <Box> </Box>
          <Box>
            <Text color="cyan">model</Text>
            <Text>  </Text>
            <Text color="whiteBright" bold>{model}</Text>
            <Text dimColor>  ·  </Text>
            {modelsOnline > 0 ? (
              <>
                <Text color="green">● online</Text>
                <Text dimColor>  ·  </Text>
                <Text color="whiteBright" bold>{modelsOnline}</Text>
                <Text dimColor> models</Text>
              </>
            ) : (
              <Text color="yellow">○ offline</Text>
            )}
          </Box>
          <Box>
            <Text dimColor>{`cwd:   ${displayCwd}`}</Text>
          </Box>
        </Box>
      </Box>
      <Box marginTop={1}>
        <Text dimColor>
          /help for commands  ·  @file to attach  ·  /sparc {'<task>'}  ·  /quit to exit
        </Text>
      </Box>
    </Box>
  );
};
