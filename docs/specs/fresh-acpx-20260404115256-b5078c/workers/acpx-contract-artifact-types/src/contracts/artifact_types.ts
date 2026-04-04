/**
 * ACPX Mission Artifact Contract Types
 * Minimal TypeScript interfaces for artifact round creation during fresh execution.
 */

export interface ArtifactMetadata {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly createdAt: number;
  readonly createdBy: string;
  readonly tags?: readonly string[];
}

export interface Artifact {
  readonly metadata: ArtifactMetadata;
  readonly content: unknown;
  readonly schema: Schema;
}

export interface Schema {
  readonly $schema: string;
  readonly type: string;
  readonly properties?: Readonly<Record<string, unknown>>;
  readonly required?: readonly string[];
}

export interface RoundArtifact extends Artifact {
  readonly roundId: string;
  readonly parentArtifactId?: string;
}

export interface FreshArtifact extends RoundArtifact {
  readonly executionId: string;
  readonly missionId: string;
}
