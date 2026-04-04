/**
 * Fresh ACPX Mission Type Contracts
 * Minimal interfaces for mission execution.
 */

export type MissionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed';

export interface RoundDefinition {
  readonly id: string;
  readonly name: string;
  readonly timeoutMs: number;
}

export interface MissionConfig {
  readonly id: string;
  readonly name: string;
  readonly rounds: readonly RoundDefinition[];
  readonly timeoutMs?: number;
}
