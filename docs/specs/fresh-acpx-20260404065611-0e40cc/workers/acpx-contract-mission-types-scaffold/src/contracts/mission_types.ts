export enum MissionStatus {
  Pending = "pending",
  Running = "running",
  Completed = "completed",
  Failed = "failed",
  Cancelled = "cancelled",
}

export interface MissionConfig {
  readonly id: string;
  readonly name: string;
  readonly timeoutMs?: number;
  readonly retries?: number;
}

export interface Mission {
  readonly id: string;
  readonly config: MissionConfig;
  readonly status: MissionStatus;
  readonly createdAt: number;
  readonly updatedAt: number;
}

export type Schema = Record<string, unknown>;
