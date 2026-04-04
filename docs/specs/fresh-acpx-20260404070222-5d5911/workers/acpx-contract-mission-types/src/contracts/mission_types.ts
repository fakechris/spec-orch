export enum MissionStatus {
  Pending = "pending",
  Active = "active",
  Completed = "completed",
  Failed = "failed",
}

export interface MissionConfig {
  id: string;
  name: string;
  status: MissionStatus;
}
