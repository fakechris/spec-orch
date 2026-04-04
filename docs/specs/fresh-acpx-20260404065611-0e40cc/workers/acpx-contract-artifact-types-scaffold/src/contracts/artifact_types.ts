/**
 * ACPX Round Artifact Type Definitions
 *
 * Minimal contract types for artifact generation during ACPX proof rounds.
 * These types align with mission_types.ts for the fresh proof run.
 */

export interface ArtifactMetadata {
  /** Unique identifier for the artifact */
  readonly id: string;
  /** Semantic version of the artifact schema */
  readonly version: string;
  /** ISO timestamp of artifact creation */
  readonly createdAt: string;
  /** Optional name for discoverability */
  readonly name?: string;
  /** Optional descriptive summary */
  readonly summary?: string;
}

/**
 * Represents a single artifact produced during a round.
 */
export interface Artifact {
  /** Artifact unique identifier */
  readonly artifactId: string;
  /** Reference to the round that produced this artifact */
  readonly roundId: string;
  /** Artifact payload content */
  readonly content: unknown;
  /** Metadata about this artifact */
  readonly metadata: ArtifactMetadata;
}

/**
 * Result of a single ACPX proof round.
 */
export interface RoundResult {
  /** Unique identifier for the round */
  readonly roundId: string;
  /** Whether the round completed successfully */
  readonly success: boolean;
  /** Artifacts produced during the round */
  readonly artifacts: ReadonlyArray<Artifact>;
  /** Optional error message if round failed */
  readonly error?: string;
  /** ISO timestamp of round completion */
  readonly completedAt: string;
}

/**
 * Schema descriptor for artifact validation.
 */
export interface Schema {
  /** Schema identifier */
  readonly $schema: string;
  /** Schema version */
  readonly version: string;
}
