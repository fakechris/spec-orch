export type MissionStatus = 'pending' | 'active' | 'completed' | 'failed';

export interface Mission {
  id: string;
  status: MissionStatus;
  createdAt: Date;
}

export interface MissionList {
  missions: Mission[];
}
