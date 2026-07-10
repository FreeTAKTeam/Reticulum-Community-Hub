-- R3AKT RCH core snapshot schema v1.
-- This database is owned by the Rust bridge/runtime state layer. It is separate
-- from the Python RCH application database unless the disabled-by-default bridge
-- is explicitly configured with this path during migration experiments.

CREATE TABLE IF NOT EXISTS rch_topics (
    topic_id TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_subscribers (
    node_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (node_id, topic_id)
);
CREATE TABLE IF NOT EXISTS rch_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    delivery_state TEXT NOT NULL DEFAULT 'queued',
    dispatch_status TEXT NOT NULL DEFAULT 'queued',
    next_attempt_at_ts_ms INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    batch_id TEXT,
    created_ts_ms INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rch_clients (
    identity TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_identity_announces (
    destination_hash TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_identity_states (
    identity TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_identity_rem_modes (
    identity TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_telemetry_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_destination TEXT NOT NULL,
    timestamp_s INTEGER NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_markers (
    object_destination_hash TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_zones (
    zone_id TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_missions (
    uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_mission_changes (
    uid TEXT PRIMARY KEY,
    mission_uid TEXT NOT NULL DEFAULT '',
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_log_entries (
    entry_uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_file_attachments (
    file_id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_eam_snapshots (
    eam_uid TEXT PRIMARY KEY,
    callsign TEXT NOT NULL,
    team_member_uid TEXT NOT NULL,
    team_uid TEXT NOT NULL,
    deleted_ts_ms INTEGER,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_teams (
    uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_mission_team_links (
    mission_uid TEXT NOT NULL,
    team_uid TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (mission_uid, team_uid)
);
CREATE TABLE IF NOT EXISTS rch_mission_zone_links (
    mission_uid TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (mission_uid, zone_id)
);
CREATE TABLE IF NOT EXISTS rch_mission_marker_links (
    mission_uid TEXT NOT NULL,
    marker_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (mission_uid, marker_id)
);
CREATE TABLE IF NOT EXISTS rch_team_members (
    uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_team_member_client_links (
    team_member_uid TEXT NOT NULL,
    client_identity TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (team_member_uid, client_identity)
);
CREATE TABLE IF NOT EXISTS rch_assets (
    asset_uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_skills (
    skill_uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_team_member_skills (
    team_member_rns_identity TEXT NOT NULL,
    skill_uid TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (team_member_rns_identity, skill_uid)
);
CREATE TABLE IF NOT EXISTS rch_task_skill_requirements (
    task_uid TEXT NOT NULL,
    skill_uid TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (task_uid, skill_uid)
);
CREATE TABLE IF NOT EXISTS rch_assignments (
    assignment_uid TEXT PRIMARY KEY,
    mission_uid TEXT NOT NULL DEFAULT '',
    task_uid TEXT NOT NULL DEFAULT '',
    team_member_rns_identity TEXT NOT NULL DEFAULT '',
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_assignment_asset_links (
    assignment_uid TEXT NOT NULL,
    asset_uid TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (assignment_uid, asset_uid)
);
CREATE TABLE IF NOT EXISTS rch_checklists (
    uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_checklist_templates (
    uid TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_checklist_columns (
    column_uid TEXT PRIMARY KEY,
    checklist_uid TEXT,
    template_uid TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_checklist_tasks (
    task_uid TEXT PRIMARY KEY,
    checklist_uid TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_checklist_cells (
    cell_uid TEXT PRIMARY KEY,
    task_uid TEXT NOT NULL,
    column_uid TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_checklist_feed_publications (
    publication_uid TEXT PRIMARY KEY,
    checklist_uid TEXT NOT NULL,
    mission_feed_uid TEXT NOT NULL,
    published_ts_ms INTEGER NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_command_results (
    command_id TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_identity_capabilities (
    identity TEXT NOT NULL,
    capability TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (identity, capability)
);
CREATE TABLE IF NOT EXISTS rch_mission_access_assignments (
    mission_uid TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (mission_uid, subject_type, subject_id)
);
CREATE TABLE IF NOT EXISTS rch_subject_operation_rights (
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (subject_type, subject_id, operation, scope_type, scope_id)
);
CREATE TABLE IF NOT EXISTS rch_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_domain_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    collection TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation_id TEXT,
    created_ts_ms INTEGER NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rch_outbound_jobs (
    job_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    delivery_state TEXT NOT NULL,
    dispatch_status TEXT NOT NULL,
    next_attempt_at_ts_ms INTEGER,
    lease_until_ts_ms INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    batch_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_ts_ms INTEGER NOT NULL,
    updated_ts_ms INTEGER NOT NULL,
    payload BLOB NOT NULL
);

INSERT OR IGNORE INTO rch_settings (setting_key, setting_value)
VALUES ('schema_version', '1');
