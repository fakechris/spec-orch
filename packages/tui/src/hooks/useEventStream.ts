import { useState, useEffect, useRef, useCallback } from "react";
import WebSocket from "ws";

export interface SpecOrchEvent {
  topic: string;
  payload: Record<string, unknown>;
  timestamp: number;
  source: string;
}

interface UseEventStreamOptions {
  url: string;
  onEvent?: (event: SpecOrchEvent) => void;
  reconnectMs?: number;
  maxHistory?: number;
}

export function useEventStream({
  url,
  onEvent,
  reconnectMs = 3000,
  maxHistory = 200,
}: UseEventStreamOptions) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<SpecOrchEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.on("open", () => setConnected(true));

    ws.on("message", (data) => {
      try {
        const event: SpecOrchEvent = JSON.parse(data.toString());
        setEvents((prev) => {
          const next = [...prev, event];
          return next.length > maxHistory ? next.slice(-maxHistory) : next;
        });
        onEvent?.(event);
      } catch {
        /* ignore malformed messages */
      }
    });

    ws.on("close", () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, reconnectMs);
    });

    ws.on("error", () => {
      ws.close();
    });
  }, [url, onEvent, reconnectMs, maxHistory]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, events };
}
