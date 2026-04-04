export interface Schema {
  id: string;
  name: string;
  version: string;
  data: unknown;
}

export type ArtifactKind = "fresh";

export interface FreshArtifact {
  readonly kind: ArtifactKind;
  readonly schema: Schema;
  readonly timestamp: number;
}

export type FreshArtifactFactory = () => FreshArtifact;
