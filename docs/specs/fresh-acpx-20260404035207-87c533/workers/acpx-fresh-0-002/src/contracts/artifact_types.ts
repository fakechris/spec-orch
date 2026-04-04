/**
 * ACPX Round Artifact Type Definitions
 * Minimal type contracts for artifact representation in ACPX execution rounds.
 */

/**
 * Unique identifier for an artifact within a round.
 */
export type ArtifactId = string & { readonly brand: unique symbol };

/**
 * Round execution marker to prove fresh execution.
 */
export interface FreshMarker {
  readonly fresh: true;
  readonly executedAt: number;
}

/**
 * Core metadata associated with an artifact.
 */
export interface ArtifactMetadata {
  readonly id: ArtifactId;
  readonly name: string;
  readonly version: number;
  readonly createdAt: number;
}

/**
 * Content payload of an artifact.
 */
export interface ArtifactContent {
  readonly format: string;
  readonly data: unknown;
}

/**
 * Complete artifact structure for ACPX rounds.
 */
export interface Artifact {
  readonly metadata: ArtifactMetadata;
  readonly content: ArtifactContent;
  readonly fresh?: FreshMarker;
}

/**
 * Schema descriptor for artifact content validation.
 */
export interface Schema {
  readonly version: string;
  readonly validators?: ReadonlyArray<string>;
}
