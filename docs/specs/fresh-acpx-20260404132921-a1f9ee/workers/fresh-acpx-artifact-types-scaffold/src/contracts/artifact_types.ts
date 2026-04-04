/**
 * Artifact Types Contract
 * Minimal TypeScript interfaces for round artifact types.
 * Supports fresh execution proof with lean, local-only definitions.
 */

export interface Schema {
  readonly version: string;
  readonly timestamp: string;
}

export interface Artifact {
  readonly id: string;
  readonly type: string;
  readonly content: unknown;
  readonly schema: Schema;
}

export interface ExecutionResult {
  readonly success: boolean;
  readonly output?: unknown;
  readonly error?: string;
  readonly durationMs?: number;
}

export interface RoundOutput {
  readonly roundId: string;
  readonly artifacts: ReadonlyArray<Artifact>;
  readonly result: ExecutionResult;
  readonly metadata?: Record<string, unknown>;
}

