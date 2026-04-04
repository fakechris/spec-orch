/**
 * Round artifact type definitions for ACPX execution schema.
 */

/**
 * RoundArtifact represents the output produced by a single mission round.
 */
export interface RoundArtifact {
  id: string;
  missionId: string;
  round: number;
  metadata: ArtifactMetadata;
  data: unknown;
  createdAt: string;
}

/**
 * ArtifactMetadata contains descriptive information about an artifact.
 */
export interface ArtifactMetadata {
  name: string;
  version: string;
  contentType: string;
  sizeBytes?: number;
  checksum?: string;
  tags?: string[];
  round?: number;
  missionId?: string;
}
