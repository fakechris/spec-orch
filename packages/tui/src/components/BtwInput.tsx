import React, { useState } from "react";
import { Box, Text, useInput } from "ink";

interface Props {
  activeIssueId: string | null;
  onSubmit: (issueId: string, message: string) => void;
  onCancel: () => void;
}

export function BtwInput({ activeIssueId, onSubmit, onCancel }: Props) {
  const [input, setInput] = useState("");

  useInput((ch, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.return) {
      const trimmed = input.trim();
      if (trimmed && activeIssueId) {
        const msg = trimmed.startsWith("/btw ")
          ? trimmed.slice(5)
          : trimmed;
        onSubmit(activeIssueId, msg);
      }
      setInput("");
      return;
    }
    if (key.backspace || key.delete) {
      setInput((prev) => prev.slice(0, -1));
      return;
    }
    if (ch && !key.ctrl && !key.meta) {
      setInput((prev) => prev + ch);
    }
  });

  if (!activeIssueId) {
    return (
      <Box paddingX={1}>
        <Text dimColor>No active issue to inject /btw context into</Text>
      </Box>
    );
  }

  return (
    <Box paddingX={1}>
      <Text color="yellow">/btw </Text>
      <Text>{input}</Text>
      <Text dimColor>█</Text>
      <Box flexGrow={1} />
      <Text dimColor>[Enter] send [Esc] cancel</Text>
    </Box>
  );
}
