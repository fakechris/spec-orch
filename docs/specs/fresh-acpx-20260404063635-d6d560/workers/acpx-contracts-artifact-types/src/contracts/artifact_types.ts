/**
 * ACPX Round Artifact Types
 * Minimal type definitions for ACPX round artifact generation.
 */

/**
 * Supported artifact kinds for ACPX round artifacts.
 */
export enum ArtifactKind {
  /** Execution plan artifact */
  Plan = "plan",
  /** Scope definition artifact */
  Scope = "scope",
  /** Implementation artifact */
  Implementation = "implementation",
  /** Verification result artifact */
  Verification = "verification",
  /** Review artifact */
  Review = "review",
  /** Error artifact */
  Error = "error",
}

/**
 * Common metadata fields for all artifacts.
 */
export interface ArtifactMetadata {
  /** Unique identifier for the artifact */
  id: string;
  /** Human-readable name of the artifact */
  name: string;
  /** Version identifier */
  version: string;
  /** Timestamp of artifact creation (ISO 8601) */
  createdAt: string;
  /** Optional description of the artifact */
  description?: string;
}

/**
 * Base artifact interface for ACPX round artifacts.
 * All artifact types should extend this interface.
 */
export interface Artifact {
  /** Kind of the artifact */
  kind: ArtifactKind;
  /** Artifact metadata */
  metadata: ArtifactMetadata;
  /** Artifact-specific payload data */
  payload: unknown;
  /** Optional schema version for the artifact */
  schemaVersion?: string;
}

/**
 * Schema definition for artifact validation.
 * Used to define the structure of artifact payloads.
 */
export interface Schema {
  /** Schema identifier */
  $id: string;
  /** Schema type */
  type: string;
  /** Optional properties definition */
  properties?: Record<string, unknown>;
  /** Optional required fields */
  required?: string[];
}
