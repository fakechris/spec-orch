import React from "react";
import { Box, Text } from "ink";
import type { LifecycleState, RunInfo } from "../hooks/useApi.js";

interface Props {
  lifecycle: LifecycleState | undefined;
  runs: RunInfo[];
}

const STATE_ICON: Record<string, string> = {
  merged: "✓",
  done: "✓",
  building: "▶",
  running: "▶",
  failed: "✗",
  pending: "○",
};

const STATE_COLOR: Record<string, string> = {
  merged: "green",
  done: "green",
  building: "yellow",
  running: "yellow",
  failed: "red",
  pending: "gray",
};

export function PipelineBar({ lifecycle, runs }: Props) {
  if (!lifecycle || lifecycle.issue_ids.length === 0) {
    return (
      <Box paddingX={1}>
        <Text dimColor>No pipeline data</Text>
      </Box>
    );
  }

  const total = lifecycle.issue_ids.length;
  const done = lifecycle.completed_issues.length;
  const barWidth = 20;
  const filled = Math.round((done / total) * barWidth);
  const bar = "■".repeat(filled) + "□".repeat(barWidth - filled);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        <Text color="cyan">Pipeline: </Text>
        <Text color="green">{bar}</Text>
        <Text>
          {" "}
          {done}/{total}
        </Text>
      </Box>
      <Box flexWrap="wrap" gap={1}>
        {lifecycle.issue_ids.map((id) => {
          const isDone = lifecycle.completed_issues.includes(id);
          const run = runs.find((r) => r.issue_id === id);
          const state = isDone ? "done" : (run?.state ?? "pending");
          const icon = STATE_ICON[state] ?? "○";
          const color = STATE_COLOR[state] ?? "gray";

          return (
            <Text key={id} color={color}>
              {icon} {id.length > 12 ? id.slice(0, 12) + "…" : id}
            </Text>
          );
        })}
      </Box>
    </Box>
  );
}
