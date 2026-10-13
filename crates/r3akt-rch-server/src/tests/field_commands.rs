#[test]
fn command_docs_show_legacy_and_mission_field_shapes() {
    let help = crate::command_help_text();
    assert!(help.contains("FIELD_COMMANDS"));
    assert!(help.contains(r#"{"9":[{"Command":"join"}]}"#));
    assert!(help.contains(r#"{"9":[{"0":"join"}]}"#));

    let examples = crate::supported_commands_document();
    assert!(examples.contains(r#"{"9":[{"Command":"join"}]}"#));
    assert!(examples.contains(r#"{"9":[{"0":"leave"}]}"#));
    assert!(examples.contains("remaining fields in the first entry become command arguments"));
    assert!(examples.contains("command_type` plus `args`"));
}
