export type Schema = Record<string, unknown>;

export interface ArtifactMetadata {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly createdAt: number;
  readonly roundId?: string;
}

export interface Artifact {
  readonly metadata: ArtifactMetadata;
  readonly schema: Schema;
  readonly data: unknown;
}

export interface RoundArtifact {
  readonly artifact: Artifact;
  readonly roundIndex: number;
  readonly producedAt: number;
}
