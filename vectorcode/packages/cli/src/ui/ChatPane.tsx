import React from "react";
import { Box, Text } from "ink";

interface ChatMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
}

interface ChatPaneProps {
  messages: ChatMessage[];
  height: number;
}

export function ChatPane({ messages, height }: ChatPaneProps) {
  return (
    <Box
      flexDirection="column"
      height={height}
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
    >
      {messages.length === 0 && (
        <Text dimColor>Type a message to start. Use /help for commands.</Text>
      )}
      {messages.map((msg, i) => {
        switch (msg.role) {
          case "user":
            return (
              <Box key={i} marginBottom={0}>
                <Text bold color="cyan">{"> "}</Text>
                <Text>{msg.content}</Text>
              </Box>
            );
          case "tool":
            return (
              <Box key={i} flexDirection="column" marginLeft={2} marginBottom={0}>
                <Text dimColor color="cyan">
                  {"▶ "}{msg.toolName || "tool"}{": "}{msg.content.slice(0, 80)}
                </Text>
                {msg.content.length > 80 && (
                  <Text dimColor>
                    {"  "}{msg.content.slice(0, 200)}
                  </Text>
                )}
              </Box>
            );
          case "assistant":
            return (
              <Box key={i} flexDirection="column" marginBottom={0}>
                <Text>{msg.content.slice(0, 600)}</Text>
                {msg.content.length > 600 && (
                  <Text dimColor>{"  "}… ({msg.content.length - 600} more chars)</Text>
                )}
              </Box>
            );
        }
      })}
    </Box>
  );
}
