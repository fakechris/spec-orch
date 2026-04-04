/**
 * ACPX Mission Contract Types
 * Minimal interfaces for fresh local-only mission execution.
 */

export const SCHEMA_VERSION = "1.0" as const;

export interface Mission {
  id: string;
  name: string;
  config: MissionConfig;
  createdAt: number;
}

export interface MissionConfig {
  rounds: Round[];
  metadata?: Record<string, unknown>;
}

export interface Round {
  id: string;
  phases: Phase[];
  metadata?: Record<string, unknown>;
}

export interface Phase {
  id: string;
  name: string;
  status: PhaseStatus;
  input?: unknown;
  output?: unknown;
}

export enum PhaseStatus {
  Pending = "pending",
  Running = "running",
  Completed = "completed",
  Failed = "failed",
}
