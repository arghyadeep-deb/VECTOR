import React from "react";
import { Box, Text } from "ink";

interface StatusLineProps {
  model: string;
  mode: string;
  tokens: number;
  cost: string;
}

export function StatusLine({ model, mode, tokens, cost }: StatusLineProps) {
  return (
    <Box width="100%" paddingX={1}>
      <Text dimColor>
        [{model}] [{mode}] [{tokens} tok] [${cost}]
      </Text>
    </Box>
  );
}
