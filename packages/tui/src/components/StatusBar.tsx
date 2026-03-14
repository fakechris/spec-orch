import React from "react";
import { Box, Text } from "ink";

interface Props {
  connected: boolean;
  mode: "normal" | "btw" | "discuss";
  missionCount: number;
}

export function StatusBar({ connected, mode, missionCount }: Props) {
  return (
    <Box paddingX={1} justifyContent="space-between">
      <Box gap={2}>
        <Text bold>spec-orch</Text>
        <Text color={connected ? "green" : "red"}>
          {connected ? "● connected" : "○ disconnected"}
        </Text>
        <Text dimColor>{missionCount} missions</Text>
      </Box>
      <Box gap={2}>
        {mode === "normal" ? (
          <Text dimColor>
            [↑↓] navigate [a]pprove [r]etry [b]tw [d]iscuss [q]uit
          </Text>
        ) : (
          <Text color="yellow">
            {mode === "btw" ? "/btw mode" : "discuss mode"} — [Esc] exit
          </Text>
        )}
      </Box>
    </Box>
  );
}
