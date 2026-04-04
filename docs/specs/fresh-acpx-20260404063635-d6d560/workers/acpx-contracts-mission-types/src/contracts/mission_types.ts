/**
 * ACPX Mission Type Definitions
 * Minimal type definitions for mission structure
 */

export enum MissionStatus {
  Pending = "pending",
  Active = "active",
  Completed = "completed",
  Failed = "failed",
  Cancelled = "cancelled",
}

export interface MissionMetadata {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface Mission<Input = unknown, Output = unknown> {
  id: string;
  status: MissionStatus;
  metadata: MissionMetadata;
  input: Input;
  output?: Output;
  error?: string;
}

export type Schema = Record<string, unknown>;
