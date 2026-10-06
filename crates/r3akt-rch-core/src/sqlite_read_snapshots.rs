use super::{
    IdentityCapabilityGrant, RchCore, RchCoreError, RchCoreSnapshot, RchSqliteStore,
    SubjectOperationRight,
};

impl RchSqliteStore {
    /// Permission reads require grants, not transport or unrelated domain history.
    pub fn load_permission_read_snapshot(&self) -> Result<RchCoreSnapshot, RchCoreError> {
        self.consistent_read(|store| {
            let mut snapshot = RchCore::new().snapshot();
            snapshot.identity_capabilities = store.load_payload_rows::<IdentityCapabilityGrant>(
                "SELECT payload FROM rch_identity_capabilities ORDER BY identity, capability",
            )?;
            snapshot.subject_operation_rights = store.load_payload_rows::<SubjectOperationRight>(
                "SELECT payload FROM rch_subject_operation_rights
                 ORDER BY subject_type, subject_id, operation, scope_type, scope_id",
            )?;
            snapshot.authorization_required = store
                .setting_value("authorization_required")?
                .is_some_and(|value| value == "true");
            Ok(snapshot)
        })
    }

    /// Ordinary HTTP registry reads do not resolve REM announce identities.
    /// Full exports and REM command authorization must use the full reader.
    pub fn load_r3akt_http_read_snapshot(&self) -> Result<RchCoreSnapshot, RchCoreError> {
        self.consistent_read(|store| store.load_r3akt_read_snapshot_rows_with_announces(false))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::IdentityAnnounceRecord;

    #[test]
    fn http_reader_skips_history_while_full_reader_preserves_exports() {
        let mut store = RchSqliteStore::in_memory().expect("store");
        let announce = IdentityAnnounceRecord {
            destination_hash: "peer".into(),
            announced_identity_hash: None,
            display_name: Some("retained".into()),
            source_interface: None,
            announce_capabilities: vec!["lxmf".into()],
            client_type: "generic_lxmf".into(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: 2,
        };
        store
            .upsert_identity_announces(std::slice::from_ref(&announce))
            .expect("history");
        assert!(
            store
                .load_r3akt_http_read_snapshot()
                .expect("HTTP")
                .identity_announces
                .is_empty()
        );
        assert_eq!(
            store
                .load_r3akt_read_snapshot()
                .expect("export")
                .identity_announces,
            [announce]
        );
        store
            .connection
            .execute("UPDATE rch_identity_announces SET payload=X'C1'", [])
            .expect("malformed history");
        assert!(store.load_r3akt_http_read_snapshot().is_ok());
        assert!(store.load_r3akt_read_snapshot().is_err());
    }

    #[test]
    fn permission_reader_exposes_malformed_grants() {
        let store = RchSqliteStore::in_memory().expect("store");
        store.connection.execute(
            "INSERT INTO rch_identity_capabilities(identity,capability,payload) VALUES ('peer','r3akt',X'C1')", [],
        ).expect("malformed relevant row");
        assert!(store.load_permission_read_snapshot().is_err());
    }

    #[test]
    fn expanded_mission_read_preserves_domain_output_without_decoding_announces() {
        let mut core = RchCore::new();
        for (kind, args) in [
            (
                "mission.registry.mission.upsert",
                serde_json::json!({
                    "uid":"mission-alpha", "mission_name":"Mission Alpha"
                }),
            ),
            (
                "mission.registry.team.upsert",
                serde_json::json!({
                    "uid":"team-alpha", "team_name":"Team Alpha", "mission_uid":"mission-alpha"
                }),
            ),
        ] {
            let command = serde_json::from_value(serde_json::json!({
                "command_id":kind, "command_type":kind, "args":args,
                "source":{"rns_identity":"ABCDEF"}, "timestamp":"2026-10-06T12:00:00Z"
            }))
            .expect("command");
            core.handle_mission_sync_command(&command);
        }
        let args = serde_json::json!({"expand":"all"});
        let expected = serde_json::json!({"missions": core.limited_mission_values(&args)});
        assert_eq!(expected["missions"][0]["teams"][0]["uid"], "team-alpha");
        let mut store = RchSqliteStore::in_memory().expect("store");
        core.save_to_sqlite(&mut store).expect("save");
        store.connection.execute(
            "INSERT INTO rch_identity_announces(destination_hash,payload,last_seen_ts_ms) VALUES ('unrelated',X'C1',0)", [],
        ).expect("unrelated malformed history");
        assert_eq!(
            store.load_mission_list_value(&args).expect("expanded list"),
            expected
        );
        let history: Vec<u8> = store
            .connection
            .query_row(
                "SELECT payload FROM rch_identity_announces WHERE destination_hash='unrelated'",
                [],
                |row| row.get(0),
            )
            .expect("retained history");
        assert_eq!(history, [0xc1]);
    }
}
