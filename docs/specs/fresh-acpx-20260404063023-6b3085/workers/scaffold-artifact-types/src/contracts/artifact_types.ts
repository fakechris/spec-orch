export interface Schema {
  version: string;
  timestamp: string;
}

export interface ArtifactMetadata {
  name: string;
  version: string;
  createdAt: string;
  missionId: string;
  roundId: string;
}

export interface Artifact {
  id: string;
  metadata: ArtifactMetadata;
  schema: Schema;
  payload: unknown;
}

export interface RoundArtifact {
  artifact: Artifact;
  proof: RoundProof;
}

export interface RoundProof {
  roundId: string;
  executedAt: string;
  executorId: string;
}

export interface FreshArtifact extends Omit<Artifact, 'metadata'> {
  metadata: Omit<ArtifactMetadata, 'version'> & {
    freshExecution: true;
  };
}
