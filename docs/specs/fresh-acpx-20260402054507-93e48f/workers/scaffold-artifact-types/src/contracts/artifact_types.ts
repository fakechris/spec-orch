/**
 * Artifact type definitions for fresh round artifacts.
 */

/**
 * Supported artifact kinds in the spec-orch system.
 */
export enum ArtifactKind {
  Specification = "specification",
  Plan = "plan",
  Scope = "scope",
  Implementation = "implementation",
  Review = "review",
  Test = "test",
}

/**
 * Core artifact interface representing a round output artifact.
 */
export interface Artifact {
  id: string;
  kind: ArtifactKind;
  name: string;
  content: string;
  metadata?: Record<string, unknown>;
}

/**
 * Round output artifact with metadata for the orch system.
 */
export interface RoundArtifact extends Artifact {
  roundId: string;
  producedAt: string;
  version: string;
}

/**
 * Schema for artifact content validation.
 */
export interface ArtifactSchema {
  kind: ArtifactKind;
  requiredFields: string[];
  optionalFields?: string[];
}

/**
 * Map of artifact kinds to their schemas.
 */
export const ARTIFACT_SCHEMAS: Record<ArtifactKind, ArtifactSchema> = {
  [ArtifactKind.Specification]: {
    kind: ArtifactKind.Specification,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
  [ArtifactKind.Plan]: {
    kind: ArtifactKind.Plan,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
  [ArtifactKind.Scope]: {
    kind: ArtifactKind.Scope,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
  [ArtifactKind.Implementation]: {
    kind: ArtifactKind.Implementation,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
  [ArtifactKind.Review]: {
    kind: ArtifactKind.Review,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
  [ArtifactKind.Test]: {
    kind: ArtifactKind.Test,
    requiredFields: ["id", "kind", "name", "content"],
    optionalFields: ["metadata"],
  },
};
