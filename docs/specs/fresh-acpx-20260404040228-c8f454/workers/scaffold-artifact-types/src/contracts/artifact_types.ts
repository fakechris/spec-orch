/**
 * Artifact type contracts for ACPX execution proof scaffold.
 * Minimal interfaces for fresh round artifact validation.
 */

export interface Artifact {
  artifactId: string;
}

export interface RoundArtifact extends Artifact {
  artifactId: string;
  round: number;
  payload: unknown;
}

export type ArtifactType = string;

export interface Schema {
  version: string;
  type: ArtifactType;
}
