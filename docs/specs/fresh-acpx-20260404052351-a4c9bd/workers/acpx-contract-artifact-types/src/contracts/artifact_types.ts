export interface Schema {
  readonly id: string;
  readonly version: string;
  readonly name: string;
}

export interface Artifact {
  readonly schema: Schema;
  readonly data: unknown;
  readonly createdAt: number;
}

export type ArtifactKind = string;

export enum ArtifactStatus {
  Pending = "pending",
  Active = "active",
  Archived = "archived",
}
