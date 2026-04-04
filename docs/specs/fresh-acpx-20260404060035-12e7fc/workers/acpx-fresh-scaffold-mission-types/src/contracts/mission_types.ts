export interface MissionConfig {
  readonly missionId: string;
  readonly name: string;
  readonly description?: string;
  readonly target?: string;
  readonly metadata?: Readonly<Record<string, string>>;
}

export type MissionState =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface MissionStatus {
  readonly state: MissionState;
  readonly progress: number;
  readonly lastUpdated: string;
  readonly error?: string;
}

export type MissionResult =
  | { readonly ok: true; readonly value: unknown }
  | { readonly ok: false; readonly error: string };

export interface Schema {
  readonly $schema?: string;
  readonly title?: string;
  readonly type?: string;
  readonly properties?: Readonly<Record<string, Schema>>;
  readonly required?: ReadonlyArray<string>;
  readonly description?: string;
}

export interface MissionManifest {
  readonly version: string;
  readonly config: Schema;
  readonly result?: Schema;
}
