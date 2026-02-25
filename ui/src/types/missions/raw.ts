export type ChecklistTemplateSourceType = "template" | "csv_import";

export type ChecklistTemplateColumnType =
  | "SHORT_STRING"
  | "LONG_STRING"
  | "INTEGER"
  | "ACTUAL_TIME"
  | "RELATIVE_TIME";

export interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
  description?: string | null;
  topic_id?: string | null;
  mission_status?: string | null;
  path?: string | null;
  classification?: string | null;
  tool?: string | null;
  keywords?: string[] | null;
  parent_uid?: string | null;
  feeds?: string[] | null;
  default_role?: string | null;
  mission_priority?: number | null;
  owner_role?: string | null;
  token?: string | null;
  invite_only?: boolean | null;
  expiration?: string | null;
  mission_rde_role?: string | null;
  asset_uids?: string[] | null;
  zones?: string[] | null;
}

export interface TopicRaw {
  TopicID?: string | null;
  TopicName?: string | null;
  TopicPath?: string | null;
  TopicDescription?: string | null;
}

export interface ChecklistCellRaw {
  column_uid?: string | null;
  value?: string | null;
}

export interface ChecklistTaskRaw {
  task_uid?: string;
  number?: number;
  due_relative_minutes?: number | null;
  user_status?: string | null;
  task_status?: string | null;
  due_dtg?: string | null;
  completed_at?: string | null;
  is_late?: boolean | null;
  completed_by_team_member_rns_identity?: string | null;
  legacy_value?: string | null;
  cells?: ChecklistCellRaw[];
}

export interface ChecklistColumnRaw {
  column_uid?: string;
  column_name?: string | null;
  column_type?: string | null;
  system_key?: string | null;
  column_editable?: boolean | null;
  display_order?: number | null;
  is_removable?: boolean | null;
  background_color?: string | null;
  text_color?: string | null;
}

export interface ChecklistRaw {
  uid?: string;
  mission_id?: string | null;
  mission_uid?: string | null;
  name?: string | null;
  description?: string | null;
  created_at?: string | null;
  created_by_team_member_rns_identity?: string | null;
  progress_percent?: number | null;
  origin_type?: string | null;
  checklist_status?: string | null;
  mode?: string | null;
  sync_state?: string | null;
  counts?: {
    pending_count?: number | null;
    late_count?: number | null;
    complete_count?: number | null;
  } | null;
  tasks?: ChecklistTaskRaw[];
  columns?: ChecklistColumnRaw[];
}

export interface TeamRaw {
  uid?: string;
  mission_uid?: string | null;
  mission_uids?: string[];
  team_name?: string | null;
  team_description?: string | null;
}

export interface TeamMemberRaw {
  uid?: string;
  team_uid?: string | null;
  rns_identity?: string | null;
  display_name?: string | null;
  role?: string | null;
  callsign?: string | null;
  client_identities?: string[];
}

export interface AssetRaw {
  asset_uid?: string;
  team_member_uid?: string | null;
  name?: string | null;
  asset_type?: string | null;
  serial_number?: string | null;
  status?: string | null;
  location?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AssignmentRaw {
  assignment_uid?: string;
  mission_uid?: string | null;
  task_uid?: string | null;
  team_member_rns_identity?: string | null;
  status?: string | null;
  notes?: string | null;
  assets?: unknown;
}

export interface DomainEventRaw {
  event_uid?: string;
  domain?: string | null;
  aggregate_type?: string | null;
  aggregate_uid?: string | null;
  event_type?: string | null;
  payload?: unknown;
  created_at?: string | null;
}

export interface MissionChangeRaw {
  uid?: string;
  mission_uid?: string | null;
  name?: string | null;
  timestamp?: string | null;
  notes?: string | null;
  change_type?: string | null;
  hashes?: unknown;
}

export interface LogEntryRaw {
  entry_uid?: string;
  mission_uid?: string | null;
  content?: string | null;
  server_time?: string | null;
  client_time?: string | null;
  content_hashes?: string[] | null;
  keywords?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ZoneRaw {
  zone_id?: string;
  name?: string;
}

export interface TemplateRaw {
  uid?: string;
  template_name?: string | null;
  description?: string | null;
  created_at?: string | null;
  created_by_team_member_rns_identity?: string | null;
  columns?: unknown;
}

export interface SkillRaw {
  skill_uid?: string;
  name?: string | null;
}

export interface TeamMemberSkillRaw {
  team_member_rns_identity?: string | null;
  skill_uid?: string | null;
  level?: number | null;
}

export interface TaskSkillRequirementRaw {
  task_uid?: string | null;
}
