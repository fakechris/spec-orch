/**
 * ACPX Artifact Type Definitions
 * Minimal type declarations for artifact scaffolding and round artifact production.
 */

/** Metadata associated with an artifact. */
export interface ArtifactMetadata {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly createdAt: string;
  readonly tags?: readonly string[];
}

/** Base artifact structure used across ACPX rounds. */
export interface Artifact {
  readonly metadata: ArtifactMetadata;
  readonly content: unknown;
  readonly schema: Schema;
}

/** Artifact produced during a specific round of processing. */
export interface RoundArtifact extends Artifact {
  readonly roundId: string;
  readonly parentArtifactId?: string;
}

/** Schema definition for artifact content validation. */
export interface Schema {
  readonly type: string;
  readonly properties?: Record<string, Schema>;
  readonly required?: readonly string[];
  readonly items?: Schema;
}

/** Enum of well-known artifact types in the ACPX system. */
export enum ArtifactType {
  Specification = "specification",
  Implementation = "implementation",
  Test = "test",
  Documentation = "documentation",
  Configuration = "configuration",
}

/** Represents a single round in the artifact production pipeline. */
export interface Round {
  readonly id: string;
  readonly stepIndex: number;
  readonly artifacts: readonly RoundArtifact[];
}

/** Input parameters for creating a new artifact. */
export type CreateArtifactInput = Readonly<{
  name: string;
  version: string;
  content: unknown;
  schema: Schema;
  tags?: readonly string[];
}>;
