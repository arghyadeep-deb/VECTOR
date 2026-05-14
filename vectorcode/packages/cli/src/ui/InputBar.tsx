import React, { useState, useCallback } from "react";
import { Box, Text, useInput } from "ink";

interface InputBarProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSubmit, disabled }: InputBarProps) {
  const [value, setValue] = useState("");

  useInput((input, key) => {
    if (disabled) return;

    if (key.return) {
      if (value.trim()) {
        onSubmit(value.trim());
        setValue("");
      }
      return;
    }

    if (key.backspace || key.delete) {
      setValue(v => v.slice(0, -1));
      return;
    }

    if (key.escape) {
      setValue("");
      return;
    }

    setValue(v => v + input);
  });

  return (
    <Box width="100%" paddingX={1}>
      <Text bold color="cyan">
        {"❯ "}
      </Text>
      <Text>{value}</Text>
      {!disabled && <Text dimColor>{"█"}</Text>}
    </Box>
  );
}
