export type MissionStatus = 'pending' | 'running' | 'completed' | 'failed';

export type MissionPriority = 'low' | 'normal' | 'high' | 'critical';

export interface Schema<M = Record<string, unknown>> {
  id: string;
  version: string;
  payload: M;
}

export interface Mission<Payload = Record<string, unknown>> {
  id: string;
  type: string;
  priority: MissionPriority;
  status: MissionStatus;
  schema: Schema<Payload>;
  createdAt: number;
  updatedAt: number;
}

export interface MissionResult<Output = unknown> {
  missionId: string;
  output: Output;
  duration: number;
  timestamp: number;
}
