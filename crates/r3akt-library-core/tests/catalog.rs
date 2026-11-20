use r3akt_library_core::{
    Availability, ItemKind, LibraryItem, LibraryQuery, Right, RppReference, Source, permits,
    rch_file_id, rch_item_id,
};
use serde_json::json;

fn item(id: u64, name: &str, media: &str, missions: &[&str], created: i64) -> LibraryItem {
    LibraryItem {
        item_id: rch_item_id(id),
        legacy_file_id: Some(id),
        kind: ItemKind::for_media_type(Some(media)),
        source: Source::Rch,
        availability: Availability::Remote,
        name: name.into(),
        media_type: Some(media.into()),
        size: 10,
        content_sha256: Some("ab".repeat(32)),
        rpp: None,
        publisher: None,
        mission_uids: missions.iter().map(|m| (*m).to_string()).collect(),
        team_uid: None,
        created_ts_ms: created,
        updated_ts_ms: created,
    }
}

fn catalog() -> Vec<LibraryItem> {
    vec![
        item(1, "map.pdf", "application/pdf", &["alpha"], 10),
        item(2, "site.jpg", "image/jpeg", &["alpha"], 20),
        item(3, "secret.pdf", "application/pdf", &["bravo"], 30),
        item(4, "legacy.txt", "text/plain", &[], 40),
    ]
}

/// The caller may read mission alpha only; nothing global.
fn alpha_reader(mission: Option<&str>, right: Right) -> bool {
    right == Right::Read && mission == Some("alpha")
}

#[test]
fn unauthorized_missions_never_appear_or_count() {
    let page = LibraryQuery::default_page().apply(catalog(), alpha_reader);
    let ids: Vec<_> = page.items.iter().map(|i| i.item_id.as_str()).collect();
    assert_eq!(
        ids,
        ["rch:2", "rch:1"],
        "newest first, bravo and global hidden"
    );
    assert_eq!(page.total, 2);
    let filtered = LibraryQuery::from_args(&json!({"mission_uid": "bravo"})).expect("query");
    assert_eq!(filtered.apply(catalog(), alpha_reader).total, 0);
}

#[test]
fn filters_search_and_pagination() {
    let all = |_: Option<&str>, _: Right| true;
    let images = LibraryQuery::from_args(&json!({"kind": "image"})).expect("query");
    assert_eq!(images.apply(catalog(), all).items[0].name, "site.jpg");
    let search = LibraryQuery::from_args(&json!({"search": "PDF"})).expect("query");
    assert_eq!(search.apply(catalog(), all).total, 2);
    let paged = LibraryQuery::from_args(&json!({"page": 2, "per_page": 3, "_rem_team_uid": "t"}))
        .expect("transport keys ignored");
    let page = paged.apply(catalog(), all);
    assert_eq!((page.items.len(), page.total, page.has_next), (1, 4, false));
    assert!(LibraryQuery::from_args(&json!({"per_page": 51})).is_err());
    assert!(LibraryQuery::from_args(&json!({"page": 0})).is_err());
    assert!(LibraryQuery::from_args(&json!({"kind": "video"})).is_err());
}

#[test]
fn rights_map_to_rch_operations() {
    assert_eq!(Right::Read.operation(), "mission.content.read");
    assert_eq!(Right::Forward.operation(), "mission.content.write");
    let shared = item(5, "a.pdf", "application/pdf", &["alpha", "bravo"], 1);
    let mut bravo_only = |m: Option<&str>, _| m == Some("bravo");
    assert!(
        permits(&shared, Right::Read, &mut bravo_only),
        "any linked mission suffices"
    );
}

#[test]
fn identities_and_metadata_are_validated() {
    let mut good = item(7, "photo.png", "image/png", &["alpha"], 1);
    good.rpp = Some(RppReference {
        package_destination: "0".repeat(32),
        file_destination: "1".repeat(32),
        manifest_hash: "2".repeat(64),
    });
    good.validate().expect("valid");
    assert_eq!(rch_file_id(&good.item_id), Some(7));
    for (mutate, why) in [
        (
            Box::new(|i: &mut LibraryItem| i.name = "../x".into()) as Box<dyn Fn(&mut LibraryItem)>,
            "traversal",
        ),
        (
            Box::new(|i: &mut LibraryItem| i.name = "a\nb".into()),
            "control",
        ),
        (
            Box::new(|i: &mut LibraryItem| i.content_sha256 = Some("AB".repeat(32))),
            "uppercase hex",
        ),
        (
            Box::new(|i: &mut LibraryItem| i.media_type = Some("text/plain".into())),
            "image kind mismatch",
        ),
        (
            Box::new(|i: &mut LibraryItem| i.rpp.as_mut().expect("rpp").manifest_hash = "z".into()),
            "rpp hex",
        ),
    ] {
        let mut bad = good.clone();
        mutate(&mut bad);
        assert!(bad.validate().is_err(), "{why}");
    }
    let json = serde_json::to_value(&good).expect("json");
    assert_eq!(json["kind"], "image");
    assert_eq!(json["availability"], "remote");
    assert_eq!(
        serde_json::from_value::<LibraryItem>(json).expect("roundtrip"),
        good
    );
}
