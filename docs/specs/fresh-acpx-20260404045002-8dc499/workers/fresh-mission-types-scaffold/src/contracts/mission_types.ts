/**
 * Mission type contracts for fresh mission execution
 */

export type MissionId = string;

export type MissionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface MissionConfig {
  id: MissionId;
  name: string;
  status: MissionStatus;
}

export interface Schema {
  MissionId: MissionId;
  MissionConfig: MissionConfig;
  MissionStatus: MissionStatus;
}
