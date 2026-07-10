CREATE TABLE IF NOT EXISTS rch_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_ts_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rch_messages_queue_due
    ON rch_messages (delivery_state, dispatch_status, next_attempt_at_ts_ms, priority, id);
CREATE INDEX IF NOT EXISTS idx_rch_messages_batch ON rch_messages (batch_id);
CREATE INDEX IF NOT EXISTS idx_rch_messages_created ON rch_messages (created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_rch_messages_queue_due_partial
    ON rch_messages (next_attempt_at_ts_ms, priority, id)
    WHERE delivery_state = 'queued';
CREATE INDEX IF NOT EXISTS idx_rch_checklist_tasks_checklist
    ON rch_checklist_tasks (checklist_uid, task_uid);
CREATE INDEX IF NOT EXISTS idx_rch_checklist_cells_task_column
    ON rch_checklist_cells (task_uid, column_uid);
CREATE INDEX IF NOT EXISTS idx_rch_checklist_columns_checklist
    ON rch_checklist_columns (checklist_uid, display_order, column_uid);
CREATE INDEX IF NOT EXISTS idx_rch_checklist_columns_template
    ON rch_checklist_columns (template_uid, display_order, column_uid);
CREATE INDEX IF NOT EXISTS idx_rch_mission_changes_mission
    ON rch_mission_changes (mission_uid, uid);
CREATE INDEX IF NOT EXISTS idx_rch_assignments_mission_task
    ON rch_assignments (mission_uid, task_uid, team_member_rns_identity, assignment_uid);
CREATE INDEX IF NOT EXISTS idx_rch_telemetry_timestamp_peer
    ON rch_telemetry_records (timestamp_s, peer_destination);
CREATE INDEX IF NOT EXISTS idx_rch_file_attachments_category
    ON rch_file_attachments (category, file_id);
CREATE INDEX IF NOT EXISTS idx_rch_eam_active_team_member
    ON rch_eam_snapshots (team_uid, team_member_uid, deleted_ts_ms);
CREATE INDEX IF NOT EXISTS idx_rch_domain_events_sequence
    ON rch_domain_events (sequence);
CREATE INDEX IF NOT EXISTS idx_rch_domain_events_collection
    ON rch_domain_events (collection, entity_id, sequence);
CREATE INDEX IF NOT EXISTS idx_rch_outbound_jobs_due
    ON rch_outbound_jobs (delivery_state, dispatch_status, next_attempt_at_ts_ms, priority, created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_rch_outbound_jobs_due_partial
    ON rch_outbound_jobs (next_attempt_at_ts_ms, priority, created_ts_ms)
    WHERE delivery_state = 'queued';
CREATE INDEX IF NOT EXISTS idx_rch_outbound_jobs_batch ON rch_outbound_jobs (batch_id);
