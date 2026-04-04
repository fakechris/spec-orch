/**
 * ACPX Mission Contract Types
 * Minimal type definitions for fresh mission creation workflow.
 */

export type MissionId = string & { readonly __brand: unique symbol };
export type MissionNamespace = string & { readonly __brand: unique symbol };

export enum MissionStatus {
  Draft = "draft",
  Pending = "pending",
  Active = "active",
  Paused = "paused",
  Completed = "completed",
  Abandoned = "abandoned",
}

export enum MissionPriority {
  Low = 0,
  Normal = 1,
  High = 2,
  Critical = 3,
}

export interface MissionMetadata {
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly version: number;
  readonly namespace: MissionNamespace;
  readonly tags?: readonly string[];
}

export interface MissionSchema {
  readonly __schema: unique symbol;
  readonly version: string;
  readonly definition: Record<string, unknown>;
}

export interface Mission<Schema extends MissionSchema = MissionSchema> {
  readonly id: MissionId;
  readonly status: MissionStatus;
  readonly priority: MissionPriority;
  readonly config: MissionConfig<Schema>;
  readonly metadata: MissionMetadata;
}

export interface MissionConfig<Schema extends MissionSchema = MissionSchema> {
  readonly name: string;
  readonly description?: string;
  readonly schema: Schema;
  readonly timeoutMs?: number;
  readonly retryPolicy?: MissionRetryPolicy;
  readonly constraints?: MissionConstraints;
}

export interface MissionRetryPolicy {
  readonly maxAttempts: number;
  readonly backoffMs?: number;
  readonly backoffMultiplier?: number;
}

export interface MissionConstraints {
  readonly maxConcurrency?: number;
  readonly deadline?: number;
}

export interface CreateMissionInput<Schema extends MissionSchema = MissionSchema> {
  readonly name: string;
  readonly description?: string;
  readonly schema: Schema;
  readonly priority?: MissionPriority;
  readonly timeoutMs?: number;
  readonly retryPolicy?: MissionRetryPolicy;
  readonly constraints?: MissionConstraints;
}
