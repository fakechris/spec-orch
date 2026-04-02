export enum MissionStatus {
  Pending = "pending",
  Active = "active",
  Paused = "paused",
  Completed = "completed",
  Failed = "failed",
}

export interface MissionMetadata {
  name: string;
  description?: string;
  tags?: string[];
  priority?: "low" | "medium" | "high";
  createdAt?: string;
  updatedAt?: string;
}

export interface MissionContext {
  missionId: string;
  status: MissionStatus;
  metadata: MissionMetadata;
  payload?: unknown;
}

export interface Mission extends MissionContext {
  status: MissionStatus.Pending;
}

export type MissionCreateInput = Omit<Mission, "missionId" | "status" | "metadata"> & {
  metadata?: Partial<MissionMetadata>;
};
