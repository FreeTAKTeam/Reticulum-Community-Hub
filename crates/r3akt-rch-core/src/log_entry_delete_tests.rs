#[test]
fn registry_log_entry_delete_removes_entry_and_rejects_unknown_uid() {
    let mut core = RchCore::new();
    core.handle_command(&command(
        "mission.registry.log_entry.upsert",
        json!({ "entry_uid": "log-del", "content": "Log event" }),
    ));
    let deleted = core.handle_command(&command(
        "mission.registry.log_entry.delete",
        json!({ "entry_uid": "log-del" }),
    ));
    assert_eq!(deleted.result.status, CommandResultStatus::Accepted);
    assert_eq!(deleted.result.result["entry_uid"], "log-del");
    assert!(core.log_entries().is_empty());
    let mut retry = command(
        "mission.registry.log_entry.delete",
        json!({ "entry_uid": "log-del" }),
    );
    retry.command_id = "cmd-delete-again".to_string();
    let again = core.handle_command(&retry);
    assert_ne!(again.result.status, CommandResultStatus::Accepted);
}
