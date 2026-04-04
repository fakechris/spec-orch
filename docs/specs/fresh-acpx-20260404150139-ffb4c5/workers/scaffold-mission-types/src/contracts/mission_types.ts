/**
 * ACPX Mission Type Definitions
 * Minimal type exports for scaffolding a fresh ACPX mission.
 */

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

/**
 * JSON Schema for a mission definition.
 * Used for validation and serialization.
 */
export interface Schema {
  /** Unique identifier for the schema version */
  version: string;
  /** Type name used in discrimination */
  type: string;
}

// ---------------------------------------------------------------------------
// Mission Types
// ---------------------------------------------------------------------------

/** Mission execution status. */
export enum MissionStatus {
  Pending = "pending",
  Running = "running",
  Completed = "completed",
  Failed = "failed",
  Cancelled = "cancelled",
}

/** Configuration passed to a mission at startup. */
export interface MissionConfig {
  /** Human-readable mission name */
  name: string;
  /** Arbitrary key-value metadata */
  metadata?: Record<string, string>;
  /** Maximum runtime in milliseconds */
  timeoutMs?: number;
}

/** The core mission object. */
export interface Mission {
  /** Globally unique mission identifier */
  id: string;
  /** Mission display name */
  name: string;
  /** Current execution status */
  status: MissionStatus;
  /** Creation timestamp (ISO 8601) */
  createdAt: string;
  /** Last update timestamp (ISO 8601) */
  updatedAt: string;
  /** Resolved schema this mission conforms to */
  schema: Schema;
  /** Mission-specific configuration */
  config: MissionConfig;
}
