/**
 * Round Artifact Contract Types
 * Minimal type definitions for fresh execution scaffold.
 */

export interface Schema {
  readonly [key: string]: unknown;
}

export type ArtifactId = string & { readonly brand: unique symbol };

export interface ArtifactData {
  readonly id: ArtifactId;
  readonly schema: Schema;
  readonly createdAt: number;
  readonly updatedAt: number;
}

export interface RoundArtifact {
  readonly artifact: ArtifactData;
  readonly roundId: string;
  readonly metadata?: Schema;
}

export type ArtifactIdFactory = (input: string) => ArtifactId;
