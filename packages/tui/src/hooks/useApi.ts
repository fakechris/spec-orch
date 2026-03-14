import { useState, useCallback, useEffect, useRef } from "react";
import http from "node:http";
import https from "node:https";

export function httpFetch(
  url: string,
  options: { method?: string; body?: string } = {},
): Promise<{ status: number; data: unknown }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === "https:" ? https : http;
    const req = lib.request(
      parsed,
      {
        method: options.method ?? "GET",
        headers: options.body
          ? { "Content-Type": "application/json" }
          : undefined,
      },
      (res) => {
        let body = "";
        res.on("data", (chunk: Buffer) => (body += chunk.toString()));
        res.on("end", () => {
          try {
            resolve({ status: res.statusCode ?? 500, data: JSON.parse(body) });
          } catch {
            resolve({ status: res.statusCode ?? 500, data: body });
          }
        });
      },
    );
    req.on("error", reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

export interface Mission {
  mission_id: string;
  status: string;
  title: string;
  spec_path: string;
}

export interface LifecycleState {
  mission_id: string;
  phase: string;
  issue_ids: string[];
  completed_issues: string[];
  error: string | null;
  updated_at: string;
}

export interface RunInfo {
  issue_id: string;
  state: string;
  branch?: string;
  started_at?: string;
}

export function useApi(baseUrl: string) {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [lifecycle, setLifecycle] = useState<Record<string, LifecycleState>>(
    {},
  );
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [m, l, r] = await Promise.all([
        httpFetch(`${baseUrl}/api/missions`),
        httpFetch(`${baseUrl}/api/lifecycle`),
        httpFetch(`${baseUrl}/api/runs`),
      ]);
      if (m.status === 200 && Array.isArray(m.data))
        setMissions(m.data as Mission[]);
      if (l.status === 200 && typeof l.data === "object")
        setLifecycle(l.data as Record<string, LifecycleState>);
      if (r.status === 200 && Array.isArray(r.data))
        setRuns(r.data as RunInfo[]);
    } catch {
      /* daemon may be unreachable */
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAll]);

  const approve = useCallback(
    async (missionId: string) => {
      return httpFetch(`${baseUrl}/api/missions/${missionId}/approve`, {
        method: "POST",
      });
    },
    [baseUrl],
  );

  const retry = useCallback(
    async (missionId: string) => {
      return httpFetch(`${baseUrl}/api/missions/${missionId}/retry`, {
        method: "POST",
      });
    },
    [baseUrl],
  );

  const discuss = useCallback(
    async (threadId: string, message: string) => {
      return httpFetch(`${baseUrl}/api/discuss`, {
        method: "POST",
        body: JSON.stringify({ thread_id: threadId, message }),
      });
    },
    [baseUrl],
  );

  const btw = useCallback(
    async (issueId: string, message: string) => {
      return httpFetch(`${baseUrl}/api/btw`, {
        method: "POST",
        body: JSON.stringify({ issue_id: issueId, message }),
      });
    },
    [baseUrl],
  );

  return {
    missions,
    lifecycle,
    runs,
    loading,
    refresh: fetchAll,
    approve,
    retry,
    discuss,
    btw,
  };
}
