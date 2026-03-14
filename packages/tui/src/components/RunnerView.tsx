import React, { useMemo } from "react";
import { Box, Text } from "ink";
import type { SpecOrchEvent } from "../hooks/useEventStream.js";
import type { LifecycleState, RunInfo } from "../hooks/useApi.js";

interface Props {
  missionId: string;
  lifecycle: LifecycleState | undefined;
  runs: RunInfo[];
  events: SpecOrchEvent[];
  height: number;
}

export function RunnerView({
  missionId,
  lifecycle,
  runs,
  events,
  height,
}: Props) {
  const issueIds = new Set(lifecycle?.issue_ids ?? []);

  const relevantEvents = useMemo(() => {
    return events.filter((e) => {
      const payload = e.payload;
      if (
        typeof payload === "object" &&
        payload !== null &&
        "mission_id" in payload
      ) {
        return payload.mission_id === missionId;
      }
      if (
        typeof payload === "object" &&
        payload !== null &&
        "issue_id" in payload
      ) {
        return issueIds.has(payload.issue_id as string);
      }
      return false;
    });
  }, [events, missionId, issueIds]);

  const lines = useMemo(() => {
    const output: Array<{ text: string; color: string }> = [];

    for (const event of relevantEvents) {
      const ts = new Date(event.timestamp * 1000)
        .toISOString()
        .slice(11, 19);

      if (event.topic === "mission.state") {
        output.push({
          text: `[${ts}] Mission ${event.payload.new_phase as string}`,
          color: "cyan",
        });
      } else if (event.topic === "issue.state") {
        output.push({
          text: `[${ts}] ${event.payload.issue_id as string}: ${event.payload.state as string} ${(event.payload.progress as string) ?? ""}`,
          color: "green",
        });
      } else if (event.topic === "builder.output") {
        const line = (event.payload.line as string) ?? "";
        output.push({ text: `  ${line}`, color: "white" });
      } else if (event.topic === "btw.injected") {
        output.push({
          text: `[${ts}] /btw injected: ${(event.payload.message as string)?.slice(0, 60)}`,
          color: "yellow",
        });
      } else if (event.topic === "gate.result") {
        const passed = event.payload.passed as boolean;
        output.push({
          text: `[${ts}] Gate: ${passed ? "PASSED" : "FAILED"}`,
          color: passed ? "green" : "red",
        });
      }
    }

    return output.slice(-(height - 4));
  }, [relevantEvents, height]);

  const activeRuns = runs.filter(
    (r) => issueIds.has(r.issue_id) && r.state !== "merged",
  );
  const activeIssue =
    activeRuns.find((r) => r.state === "building" || r.state === "running") ??
    activeRuns[0];

  return (
    <Box flexDirection="column" flexGrow={1} borderStyle="single" borderColor="green" paddingX={1}>
      <Box>
        <Text bold color="green">
          Runner Output
        </Text>
        {activeIssue ? (
          <Text dimColor>
            {" "}
            — {activeIssue.issue_id} [{activeIssue.state}]
          </Text>
        ) : null}
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        {lines.length === 0 ? (
          <Text dimColor>Waiting for events...</Text>
        ) : (
          lines.map((line, i) => (
            <Text key={i} color={line.color} wrap="truncate">
              {line.text}
            </Text>
          ))
        )}
      </Box>
    </Box>
  );
}
