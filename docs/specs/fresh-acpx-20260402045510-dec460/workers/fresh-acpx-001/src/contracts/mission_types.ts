export enum MissionState {
  Pending = "pending",
  Active = "active",
  Paused = "paused",
  Completed = "completed",
  Failed = "failed",
}

export interface MissionMetadata {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  ownerId: string;
  tags?: string[];
}

export interface RoundArtifact {
  roundIndex: number;
  schema: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface RoundArtifactSchema {
  type: string;
  properties: Record<string, unknown>;
  required?: string[];
}

export interface MissionContract {
  metadata: MissionMetadata;
  state: MissionState;
  currentRound: number;
  totalRounds: number;
  artifacts: RoundArtifact[];
}

export type { RoundArtifactSchema as ArtifactSchema };
