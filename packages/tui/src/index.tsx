#!/usr/bin/env node
import React from "react";
import { withFullScreen } from "fullscreen-ink";
import { App } from "./App.js";

const DEFAULT_PORT = 8420;

function parseArgs(): { apiUrl: string; wsUrl: string } {
  const args = process.argv.slice(2);
  let port = DEFAULT_PORT;
  let host = "127.0.0.1";

  for (let i = 0; i < args.length; i++) {
    if ((args[i] === "--port" || args[i] === "-p") && args[i + 1]) {
      const parsed = parseInt(args[i + 1]!, 10);
      if (!Number.isNaN(parsed)) port = parsed;
      i++;
    }
    if ((args[i] === "--host" || args[i] === "-h") && args[i + 1]) {
      host = args[i + 1]!;
      i++;
    }
  }

  return {
    apiUrl: `http://${host}:${port}`,
    wsUrl: `ws://${host}:${port}/ws`,
  };
}

async function main() {
  const { apiUrl, wsUrl } = parseArgs();

  const ink = withFullScreen(<App apiUrl={apiUrl} wsUrl={wsUrl} />);
  await ink.start();
  await ink.waitUntilExit();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
