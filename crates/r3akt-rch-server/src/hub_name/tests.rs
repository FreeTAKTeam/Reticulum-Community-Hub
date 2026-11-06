use super::*;

fn fixture() -> (std::path::PathBuf, AppState) {
    let dir = std::env::temp_dir().join(format!("rch-hub-name-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let state = AppState::from_sqlite_path(dir.join("rch.db"))
        .unwrap()
        .with_config_path(dir.join("config.ini"));
    (dir, state)
}

#[test]
fn hub_name_precedence_survives_restart_and_upgrade_conflicts() {
    for (saved, body, expected) in [
        (
            Some("RCH AltreAlternative"),
            "[hub]\ndisplay_name = R3AKT server\nname = stale\nidentity_path = preserved.identity\n",
            "RCH AltreAlternative",
        ),
        (
            None,
            "[hub]\ndisplay_name = stale\nname = Named Hub\n",
            "Named Hub",
        ),
        (None, "[hub]\ndisplay_name = Display Hub\n", "Display Hub"),
        (
            None,
            "\u{feff}[ hub ]\ndisplay_name = \"Quoted Hub\"\n",
            "Quoted Hub",
        ),
        (None, "[hub]\n", "RCH"),
    ] {
        let (dir, state) = fixture();
        let config = dir.join("config.ini");
        std::fs::write(&config, body).unwrap();
        std::fs::write(dir.join("preserved.identity"), b"existing identity bytes").unwrap();
        if let Some(saved) = saved {
            with_core_store_write(&state, |store| {
                store.set_setting_value(HUB_NAME_SETTING, saved)
            })
            .unwrap();
        }
        for _ in 0..2 {
            assert_eq!(state.reconcile_hub_display_name().unwrap(), expected);
            let restored = AppState::from_sqlite_path(dir.join("rch.db"))
                .unwrap()
                .with_config_path(&config);
            assert_eq!(resolve(&restored).unwrap(), expected);
            assert_eq!(
                crate::app_info_payload(&restored).unwrap()["display_name"],
                expected
            );
            let content = std::fs::read_to_string(&config).unwrap();
            for key in ["name", "display_name"] {
                assert_eq!(
                    config_text_section_value(&content, "hub", &[key]).as_deref(),
                    Some(expected)
                );
            }
            // Package upgrades may preserve the DB but reinstall conflicting defaults.
            std::fs::write(&config, body).unwrap();
        }
        assert_eq!(
            std::fs::read(dir.join("preserved.identity")).unwrap(),
            b"existing identity bytes"
        );
        std::fs::remove_dir_all(dir).unwrap();
    }
}

#[test]
fn config_alias_edits_are_order_independent_and_reject_competing_names() {
    let (dir, state) = fixture();
    std::fs::write(
        dir.join("config.ini"),
        "[hub]\nname = Old\ndisplay_name = Old\n",
    )
    .unwrap();
    with_core_store_write(&state, |store| {
        store.set_setting_value(HUB_NAME_SETTING, "Saved")
    })
    .unwrap();
    for (body, expected) in [
        ("[hub]\nname = New\ndisplay_name = Old\n", "New"),
        ("[hub]\nname: New\ndisplay_name: Old\n", "New"),
        ("[hub]\ndisplay_name = New\nname = Old\n", "New"),
        ("[hub]\nname = New\ndisplay_name = New\n", "New"),
        ("[hub]\nname = Old\ndisplay_name = Old\n", "Saved"),
        ("[other]\nname = Ignored\n", "Saved"),
    ] {
        assert_eq!(renamed(&state, body).unwrap(), expected);
    }
    assert!(renamed(&state, "[hub]\nname = One\ndisplay_name = Two\n").is_err());
    assert!(renamed(&state, "[hub]\nname = \n").is_err());
    for name in ["", "\n", &"x".repeat(81)] {
        assert!(validate(name).is_err());
    }
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn failed_database_save_restores_config_and_canonical_name() {
    let (dir, state) = fixture();
    state.reconcile_hub_display_name().unwrap();
    let original = std::fs::read(dir.join("config.ini")).unwrap();
    let db = rusqlite::Connection::open(dir.join("rch.db")).unwrap();
    db.execute_batch("CREATE TRIGGER reject_hub_name BEFORE INSERT ON rch_settings WHEN NEW.setting_key = 'hub_name' BEGIN SELECT RAISE(ABORT, 'fixture rejects name'); END;").unwrap();
    assert!(save(&state, "[hub]\nname = New\n", "New").is_err());
    assert_eq!(std::fs::read(dir.join("config.ini")).unwrap(), original);
    assert_eq!(resolve(&state).unwrap(), "RCH");
    std::fs::remove_dir_all(dir).unwrap();
}
