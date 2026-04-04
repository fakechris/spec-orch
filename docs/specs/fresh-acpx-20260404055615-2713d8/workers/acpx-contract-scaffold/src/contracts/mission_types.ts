/**
 * Core mission type definitions for ACPX execution schema.
 */

/**
 * Mission represents the top-level unit of work in the ACPX system.
 */
export interface Mission {
  id: string;
  name: string;
  config: MissionConfig;
  state: MissionState;
  createdAt: string;
  updatedAt: string;
}

/**
 * MissionConfig contains parameters that control mission execution behavior.
 */
export interface MissionConfig {
  maxRounds?: number;
  timeoutMs?: number;
  retryPolicy?: RetryPolicy;
  schema?: Schema;
}

/**
 * MissionState tracks the current execution state of a mission.
 */
export interface MissionState {
  status: MissionStatus;
  currentRound: number;
  completedRounds: number[];
  artifacts: string[];
  errors: MissionError[];
}

/**
 * RetryPolicy defines how failed operations should be retried.
 */
export interface RetryPolicy {
  maxAttempts: number;
  backoffMs: number;
  backoffMultiplier?: number;
}

/**
 * Schema defines the structure for mission input/output validation.
 */
export interface Schema {
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
}

/**
 * MissionStatus represents possible mission lifecycle states.
 */
export type MissionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed';

/**
 * MissionError captures error information during mission execution.
 */
export interface MissionError {
  round: number;
  message: string;
  timestamp: string;
  recoverable: boolean;
}
