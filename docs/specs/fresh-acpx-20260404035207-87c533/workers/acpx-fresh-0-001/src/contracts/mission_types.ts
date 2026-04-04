/**
 * ACPX Mission Type Definitions
 * Minimal type scaffold for fresh mission creation.
 */

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export interface Schema {
  /** Unique mission identifier */
  id: string;
  /** Human-readable mission name */
  name: string;
  /** Mission version string (semver) */
  version: string;
  /** Optional mission description */
  description?: string;
  /** Execution configuration */
  config: MissionConfig;
  /** Input schema definition */
  input: Record<string, unknown>;
  /** Output schema definition */
  output: Record<string, unknown>;
}

/** Mission execution configuration */
export interface MissionConfig {
  /** Maximum execution time in milliseconds */
  timeoutMs: number;
  /** Retry policy for failed missions */
  retryPolicy?: RetryPolicy;
  /** Environment variables required by the mission */
  envVars?: Record<string, string>;
}

/** Retry policy for mission execution */
export interface RetryPolicy {
  /** Maximum number of retry attempts */
  maxAttempts: number;
  /** Initial backoff delay in milliseconds */
  initialDelayMs: number;
  /** Maximum backoff delay in milliseconds */
  maxDelayMs: number;
}

// ---------------------------------------------------------------------------
// Mission Lifecycle
// ---------------------------------------------------------------------------

/** Mission execution status */
export type MissionStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

/** Mission result payload */
export interface MissionResult {
  status: MissionStatus;
  output?: Record<string, unknown>;
  error?: MissionError;
  startedAt: string; // ISO-8601
  completedAt?: string; // ISO-8601
}

/** Mission execution error */
export interface MissionError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Contract Tokens (for type-level validation)
// ---------------------------------------------------------------------------

/** Token identifying this as an ACPX mission contract */
export const CONTRACT_TYPE = 'acpx.mission.v1' as const;

/** Symbol for nominal typing of mission schemas */
export const SCHEMA_TYPE = Symbol.for('Schema');
