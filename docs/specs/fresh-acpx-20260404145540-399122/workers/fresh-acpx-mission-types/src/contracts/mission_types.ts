export enum MissionStatus {
  Pending = "pending",
  Running = "running",
  Completed = "completed",
  Failed = "failed",
  Cancelled = "cancelled",
}

export enum MissionPriority {
  Low = 0,
  Normal = 1,
  High = 2,
  Critical = 3,
}

export interface MissionConfig {
  name: string;
  description?: string;
  priority?: MissionPriority;
  timeoutMs?: number;
  tags?: string[];
}

export interface Mission {
  id: string;
  config: MissionConfig;
  status: MissionStatus;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
}
