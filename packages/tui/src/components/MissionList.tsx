import React from "react";
import { Box, Text } from "ink";
import type { Mission, LifecycleState } from "../hooks/useApi.js";

const PHASE_COLORS: Record<string, string> = {
  approved: "yellow",
  planning: "cyan",
  planned: "blue",
  promoting: "cyan",
  executing: "green",
  all_done: "greenBright",
  retrospecting: "magenta",
  evolving: "magentaBright",
  completed: "gray",
  failed: "red",
};

const PHASE_ICONS: Record<string, string> = {
  approved: "◎",
  planning: "⟳",
  planned: "☰",
  promoting: "⟳",
  executing: "▶",
  all_done: "✓",
  retrospecting: "◈",
  evolving: "◈",
  completed: "●",
  failed: "✗",
};

interface Props {
  missions: Mission[];
  lifecycle: Record<string, LifecycleState>;
  selectedIndex: number;
  width: number;
}

export function MissionList({
  missions,
  lifecycle,
  selectedIndex,
  width,
}: Props) {
  if (missions.length === 0) {
    return (
      <Box
        flexDirection="column"
        width={width}
        borderStyle="single"
        borderColor="gray"
        paddingX={1}
      >
        <Text bold>Missions</Text>
        <Text dimColor>No missions found</Text>
      </Box>
    );
  }

  return (
    <Box
      flexDirection="column"
      width={width}
      borderStyle="single"
      borderColor="cyan"
      paddingX={1}
    >
      <Text bold color="cyan">
        Missions
      </Text>
      {missions.map((m, i) => {
        const isSelected = i === selectedIndex;
        const lc = lifecycle[m.mission_id];
        const phase = lc?.phase ?? m.status;
        const color = PHASE_COLORS[phase] ?? "white";
        const icon = PHASE_ICONS[phase] ?? "○";

        const progress = lc
          ? `${lc.completed_issues.length}/${lc.issue_ids.length}`
          : "";

        return (
          <Box key={m.mission_id}>
            <Text color={isSelected ? "yellowBright" : "white"}>
              {isSelected ? "▸ " : "  "}
            </Text>
            <Text color={color}>
              {icon}{" "}
            </Text>
            <Text
              color={isSelected ? "yellowBright" : "white"}
              bold={isSelected}
              wrap="truncate"
            >
              {m.title || m.mission_id}
            </Text>
            {progress ? (
              <Text dimColor> [{progress}]</Text>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}
