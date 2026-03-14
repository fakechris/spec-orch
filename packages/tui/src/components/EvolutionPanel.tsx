import React, { useState, useEffect, useCallback } from "react";
import { Box, Text } from "ink";

interface VariantInfo {
  variant_id: string;
  total_runs: number;
  successful_runs: number;
  success_rate: number;
  is_active: boolean;
  is_candidate: boolean;
  rationale: string;
}

interface EvolutionData {
  prompt_variants: number;
  scoper_hints: number;
  policies: number;
  success_rate: number;
  total_runs: number;
  variants: VariantInfo[];
  run_trend: Array<{ run: string; ok: boolean; cumulative_rate: number }>;
}

interface Props {
  apiUrl: string;
}

export function EvolutionPanel({ apiUrl }: Props) {
  const [data, setData] = useState<EvolutionData | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const http = await import("node:http");
      const url = new URL(`${apiUrl}/api/evolution`);
      const res = await new Promise<string>((resolve, reject) => {
        http
          .get(url, (r) => {
            let body = "";
            r.on("data", (chunk: Buffer) => (body += chunk.toString()));
            r.on("end", () => resolve(body));
          })
          .on("error", reject);
      });
      setData(JSON.parse(res));
    } catch {
      /* daemon unreachable */
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (!data) {
    return (
      <Box flexDirection="column" borderStyle="single" borderColor="magenta" paddingX={1}>
        <Text bold color="magenta">
          Evolution
        </Text>
        <Text dimColor>Loading...</Text>
      </Box>
    );
  }

  const trendWidth = 20;
  const trend = data.run_trend.slice(-trendWidth);
  const trendBar = trend.map((t) => (t.ok ? "▓" : "░")).join("");

  return (
    <Box flexDirection="column" borderStyle="single" borderColor="magenta" paddingX={1}>
      <Text bold color="magenta">
        Evolution
      </Text>

      <Box gap={3}>
        <Text>
          <Text color="cyan">Runs:</Text> {data.total_runs}
        </Text>
        <Text>
          <Text color="cyan">Rate:</Text>{" "}
          <Text color={data.success_rate >= 70 ? "green" : data.success_rate >= 40 ? "yellow" : "red"}>
            {data.success_rate}%
          </Text>
        </Text>
        <Text>
          <Text color="cyan">Prompts:</Text> {data.prompt_variants}
        </Text>
        <Text>
          <Text color="cyan">Hints:</Text> {data.scoper_hints}
        </Text>
        <Text>
          <Text color="cyan">Policies:</Text> {data.policies}
        </Text>
      </Box>

      {trend.length > 0 ? (
        <Box>
          <Text dimColor>Trend: </Text>
          <Text color="green">{trendBar}</Text>
          <Text dimColor> ({trend.length} recent)</Text>
        </Box>
      ) : null}

      {data.variants.length > 0 ? (
        <Box flexDirection="column">
          {data.variants.slice(0, 5).map((v) => (
            <Box key={v.variant_id} gap={1}>
              <Text color={v.is_active ? "green" : v.is_candidate ? "yellow" : "gray"}>
                {v.is_active ? "●" : v.is_candidate ? "◎" : "○"}
              </Text>
              <Text bold>{v.variant_id}</Text>
              <Text color={v.success_rate >= 70 ? "green" : v.success_rate >= 40 ? "yellow" : "red"}>
                {v.success_rate}%
              </Text>
              <Text dimColor>
                ({v.successful_runs}/{v.total_runs})
              </Text>
              {v.rationale ? (
                <Text dimColor wrap="truncate">
                  {v.rationale.slice(0, 40)}
                </Text>
              ) : null}
            </Box>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}
