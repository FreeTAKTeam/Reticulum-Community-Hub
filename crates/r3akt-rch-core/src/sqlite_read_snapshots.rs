use super::{
    IdentityAnnounceRecord, IdentityCapabilityGrant, RchCore, RchCoreError, RchCoreSnapshot,
    RchSqliteStore, SubjectOperationRight, decode_msgpack,
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

    /// Filter the indexed freshness range before decoding, then retain only REM
    /// payloads. Restore raw destination order for the peer selector's tie rules.
    pub fn load_rem_peer_read_snapshot(
        &self,
        cutoff_ms: i64,
    ) -> Result<RchCoreSnapshot, RchCoreError> {
        self.consistent_read(|store| {
            let mut snapshot = RchCore::new().snapshot();
            let mut statement = store.connection.prepare(
                "SELECT payload FROM rch_identity_announces WHERE last_seen_ts_ms >= ?1",
            )?;
            let mut rows = statement.query([cutoff_ms])?;
            while let Some(row) = rows.next()? {
                let payload: Vec<u8> = row.get(0)?;
                let record: IdentityAnnounceRecord = decode_msgpack(&payload)?;
                if record.client_type.trim().eq_ignore_ascii_case("rem") {
                    snapshot.identity_announces.push(record);
                }
            }
            snapshot
                .identity_announces
                .sort_by(|left, right| left.destination_hash.cmp(&right.destination_hash));
            snapshot.identity_states = store.load_identity_states()?;
            snapshot.identity_rem_modes = store.load_identity_rem_modes()?;
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
    #[test]
    fn rem_reader_preserves_raw_order_and_exact_cutoff_without_retaining_generic_history() {
        let mut store = RchSqliteStore::in_memory().expect("store");
        let make = |destination: &str, last_seen, client_type: &str| IdentityAnnounceRecord {
            destination_hash: destination.into(),
            announced_identity_hash: Some(" Owner ".into()),
            display_name: None,
            source_interface: None,
            announce_capabilities: vec![],
            client_type: client_type.into(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: last_seen,
        };
        let older = make("A", 100, " ReM ");
        let newer = make("z", 300, "rem");
        store
            .upsert_identity_announces(&[
                newer.clone(),
                make("stale", 99, "rem"),
                older.clone(),
                make("generic", 200, "generic_lxmf"),
            ])
            .expect("history");
        let before = store.load_identity_announces().expect("full history");
        assert_eq!(
            store
                .load_rem_peer_read_snapshot(100)
                .expect("fresh REM")
                .identity_announces,
            [older, newer]
        );
        assert_eq!(store.load_identity_announces().expect("unchanged"), before);
        store
            .connection
            .execute(
                "UPDATE rch_identity_announces SET payload=X'C1' WHERE destination_hash='stale'",
                [],
            )
            .expect("stale corruption");
        assert!(store.load_rem_peer_read_snapshot(100).is_ok());
        store
            .connection
            .execute(
                "UPDATE rch_identity_announces SET payload=X'C1' WHERE destination_hash='generic'",
                [],
            )
            .expect("fresh corruption");
        assert!(store.load_rem_peer_read_snapshot(100).is_err());
    }
}
