export interface Artifact {
  readonly id: string;
  readonly version: string;
  readonly createdAt: number;
}

export interface ArtifactMetadata {
  readonly artifactId: string;
  readonly name: string;
  readonly description: string;
  readonly tags: readonly string[];
  readonly round: number;
}

export interface Schema {
  readonly type: string;
  readonly properties: Record<string, unknown>;
  readonly required: readonly string[];
}

export interface RoundArtifact extends Artifact {
  readonly round: number;
  readonly inputSchema: Schema;
  readonly outputSchema: Schema;
  readonly data: unknown;
  readonly metadata: ArtifactMetadata;
}

export enum ArtifactType {
  Round = "round",
  Metadata = "metadata",
  Schema = "schema",
}
