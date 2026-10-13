use crate::*;

fn recovery_fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-receipt-recovery-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

#[test]
fn display_names_do_not_merge_registered_broadcast_recipients() {
    let (state, directory) = recovery_fixture();
    let now = unix_now_ms();
    for (id, capabilities) in [
        ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Vec::new()),
        (
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            vec!["voice".to_string(), "telephony".to_string()],
        ),
    ] {
        let mut client = ClientRecord::new(id.to_string(), now);
        client.display_name = Some("Shared display name".to_string());
        client.announce_capabilities = capabilities;
        state
            .clients
            .write()
            .expect("clients")
            .insert(id.to_string(), client);
    }
    let message = record_outbound_message_with_metadata(
        &state,
        "broadcast to registered recipients",
        None,
        None,
        Vec::new(),
        false,
        json!({}),
    )
    .expect("queue broadcast");
    assert_eq!(
        outbound_destinations(&state, &message).expect("recipients"),
        [
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_string(),
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_string()
        ]
    );
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
