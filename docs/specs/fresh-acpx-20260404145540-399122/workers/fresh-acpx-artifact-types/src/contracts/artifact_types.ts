export enum ArtifactType {
  Spec = "spec",
  Plan = "plan",
  Scope = "scope",
  Build = "build",
  Verify = "verify",
  Review = "review",
  Test = "test",
  Document = "document",
  Config = "config",
  Other = "other",
}

export interface Artifact {
  id: string;
  type: ArtifactType;
  name: string;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface RoundArtifact {
  roundId: string;
  artifacts: Artifact[];
}
