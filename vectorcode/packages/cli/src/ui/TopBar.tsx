import React from "react";
import { Box, Text } from "ink";

interface TopBarProps {
  model: string;
  mode: string;
  tokens: number;
  cost: string;
}

const CYAN = "\x1b[96m";

export function TopBar({ model, mode, tokens, cost }: TopBarProps) {
  return (
    <Box
      width="100%"
      borderStyle="single"
      borderColor="cyan"
      paddingX={1}
      paddingY={0}
    >
      <Box width="33%">
        <Text bold color="cyan">
          {CYAN}VectorCode{CYAN}
        </Text>
      </Box>
      <Box width="34%" justifyContent="center">
        <Text color="cyan" bold>
          {model}
        </Text>
      </Box>
      <Box width="33%" justifyContent="flex-end">
        <Text color="cyan">
          {mode}  │  {tokens} tok  │  ${cost}
        </Text>
      </Box>
    </Box>
  );
}
