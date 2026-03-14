import React, { useState, useCallback, useMemo } from "react";
import { Box, Text, useApp, useInput } from "ink";
import { useScreenSize } from "fullscreen-ink";
import { useApi } from "./hooks/useApi.js";
import { useEventStream } from "./hooks/useEventStream.js";
import { MissionList } from "./components/MissionList.js";
import { RunnerView } from "./components/RunnerView.js";
import { PipelineBar } from "./components/PipelineBar.js";
import { BtwInput } from "./components/BtwInput.js";
import { StatusBar } from "./components/StatusBar.js";

interface AppProps {
  apiUrl: string;
  wsUrl: string;
}

type Mode = "normal" | "btw" | "discuss";

export function App({ apiUrl, wsUrl }: AppProps) {
  const { exit } = useApp();
  const { height, width } = useScreenSize();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mode, setMode] = useState<Mode>("normal");

  const api = useApi(apiUrl);
  const { connected, events } = useEventStream({ url: wsUrl });

  const selectedMission = api.missions[selectedIndex];
  const selectedLc = selectedMission
    ? api.lifecycle[selectedMission.mission_id]
    : undefined;

  const activeIssueId = useMemo(() => {
    if (!selectedLc) return null;
    const running = selectedLc.issue_ids.find(
      (id) => !selectedLc.completed_issues.includes(id),
    );
    return running ?? null;
  }, [selectedLc]);

  const handleBtwSubmit = useCallback(
    async (issueId: string, message: string) => {
      await api.btw(issueId, message);
      setMode("normal");
    },
    [api],
  );

  useInput(
    (input, key) => {
      if (mode !== "normal") return;

      if (input === "q" || (input === "c" && key.ctrl)) {
        exit();
        return;
      }

      if (key.upArrow) {
        setSelectedIndex((i) => Math.max(0, i - 1));
      }
      if (key.downArrow && api.missions.length > 0) {
        setSelectedIndex((i) => Math.min(api.missions.length - 1, i + 1));
      }

      if (input === "a" && selectedMission) {
        api.approve(selectedMission.mission_id);
      }
      if (input === "r" && selectedMission) {
        api.retry(selectedMission.mission_id);
      }
      if (input === "b") {
        setMode("btw");
      }
    },
    { isActive: mode === "normal" },
  );

  const sidebarWidth = Math.min(Math.max(Math.floor(width * 0.3), 24), 40);

  return (
    <Box flexDirection="column" width={width} height={height}>
      {/* Header */}
      <Box
        borderStyle="round"
        borderColor="cyan"
        paddingX={1}
        justifyContent="space-between"
        flexShrink={0}
      >
        <Box gap={1}>
          <StatusBar
            connected={connected}
            mode={mode}
            missionCount={api.missions.length}
          />
        </Box>
      </Box>

      {/* Main content */}
      <Box flexGrow={1}>
        {/* Left: Mission list */}
        <MissionList
          missions={api.missions}
          lifecycle={api.lifecycle}
          selectedIndex={selectedIndex}
          width={sidebarWidth}
        />

        {/* Right: Runner output + Pipeline */}
        <Box flexDirection="column" flexGrow={1}>
          <RunnerView
            missionId={selectedMission?.mission_id ?? ""}
            lifecycle={selectedLc}
            runs={api.runs}
            events={events}
            height={Math.max(height - 10, 8)}
          />
          <PipelineBar lifecycle={selectedLc} runs={api.runs} />
        </Box>
      </Box>

      {/* Footer: btw input or hotkey hints */}
      {mode === "btw" ? (
        <BtwInput
          activeIssueId={activeIssueId}
          onSubmit={handleBtwSubmit}
          onCancel={() => setMode("normal")}
        />
      ) : (
        <Box paddingX={1} borderStyle="single" borderColor="gray">
          {selectedMission ? (
            <Box gap={2}>
              <Text dimColor>
                {selectedMission.mission_id}: {selectedLc?.phase ?? selectedMission.status}
              </Text>
              {selectedLc?.error ? (
                <Text color="red">Error: {selectedLc.error.slice(0, 50)}</Text>
              ) : null}
            </Box>
          ) : (
            <Text dimColor>No mission selected</Text>
          )}
        </Box>
      )}
    </Box>
  );
}
