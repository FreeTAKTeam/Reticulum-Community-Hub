export interface MissionDomainView {
  uid: string;
  mission_name: string;
  description: string;
  topic_id: string;
  mission_status: string;
  zone_ids: string[];
  asset_uids: string[];
}

export interface ChecklistTaskView {
  task_uid: string;
  number: number;
  status: string;
  due_dtg: string;
  due_relative_minutes: number | null;
  completed_at: string;
  assignee: string;
}

export interface ChecklistDomainView {
  uid: string;
  mission_uid: string;
  name: string;
  description: string;
  created_at: string;
  mode: string;
  sync_state: string;
  checklist_status: string;
  pending_count: number;
  late_count: number;
  complete_count: number;
  tasks: ChecklistTaskView[];
}

export interface TeamDomainView {
  uid: string;
  mission_uids: string[];
  name: string;
  description: string;
}

export interface TeamMemberDomainView {
  uid: string;
  team_uid: string;
  display_name: string;
  role: string;
  rns_identity: string;
}

export interface AssetDomainView {
  uid: string;
  mission_uid: string;
  name: string;
  asset_type: string;
  status: string;
}

export interface AssignmentDomainView {
  uid: string;
  mission_uid: string;
  task_uid: string;
  team_member_rns_identity: string;
  status: string;
  assets: string[];
}

export interface ZoneDomainView {
  uid: string;
  name: string;
  assigned: boolean;
}

export interface AuditEventDomainView {
  uid: string;
  mission_uid: string;
  timestamp: string;
  type: string;
  message: string;
}
