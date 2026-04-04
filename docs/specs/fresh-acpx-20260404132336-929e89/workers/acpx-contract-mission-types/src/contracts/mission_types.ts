/**
 * ACPX Mission Type Interfaces
 * Core mission type definitions for fresh mission creation workflow.
 */

/**
 * Mission status states
 */
export enum MissionStatus {
  Pending = "pending",
  Active = "active",
  Completed = "completed",
  Failed = "failed",
  Cancelled = "cancelled",
}

/**
 * Mission configuration
 */
export interface MissionConfig {
  name: string;
  description?: string;
  priority?: number;
  timeout?: number;
  retries?: number;
  metadata?: Record<string, unknown>;
}

/**
 * Core mission interface
 */
export interface Mission {
  id: string;
  status: MissionStatus;
  config: MissionConfig;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * Mission creation payload
 */
export interface CreateMissionPayload {
  config: MissionConfig;
}

/**
 * Mission update payload
 */
export interface UpdateMissionPayload {
  status?: MissionStatus;
  config?: Partial<MissionConfig>;
}
