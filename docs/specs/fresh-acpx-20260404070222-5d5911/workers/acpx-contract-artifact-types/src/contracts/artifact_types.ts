export interface Artifact {
  id: string;
  type: string;
  data: unknown;
}

export interface RoundArtifact {
  roundId: string;
  artifacts: Artifact[];
  metadata?: Record<string, unknown>;
}
