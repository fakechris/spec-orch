export enum MissionStatus {
  Pending = "pending",
  Active = "active",
  Completed = "completed",
  Failed = "failed",
}

export enum MissionPriority {
  Low = "low",
  Medium = "medium",
  High = "high",
  Critical = "critical",
}

export interface Mission {
  id: string;
  type: string;
  status: MissionStatus;
  priority: MissionPriority;
  title: string;
  description: string;
}

export interface MissionSchema {
  mission: Mission;
}
