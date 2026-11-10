use r3akt_profile_rch::teams::{
    CANONICAL_TEAMS, canonical_team_color_for_uid, canonical_team_for_uid,
    canonical_team_uid_for_color, is_canonical_team_uid,
};

const EXPECTED: [(&str, &str); 13] = [
    ("d6b6e188b910d6bdd24d04b7a7ec5444", "YELLOW"),
    ("65ce79a3a3e4b51ec0ec52d1d3d2b0b9", "RED"),
    ("43341e5c822d99857fa6e8641f2ca9c0", "BLUE"),
    ("a83eb640e4c4884be14831e3d7ef5ae0", "ORANGE"),
    ("7ac50a910f42b06cd9cb68dad3def681", "MAGENTA"),
    ("372824ef4f15881291455562f7570233", "MAROON"),
    ("4bf2a1d2217c8668942658137f2a6824", "PURPLE"),
    ("cbb35fc9a8f5a91d7bd2b5e5b644edcd", "DARK_BLUE"),
    ("d4cd5030b68df059ec6beabe416dd6a6", "CYAN"),
    ("4d7a7a974beec395bf83491604768499", "TEAL"),
    ("612a32262163b73a80eca944c2158546", "GREEN"),
    ("341653613d4c76d56bee99c1f38177b1", "DARK_GREEN"),
    ("4efe72ac30f5b85142fdcab6d96c7631", "BROWN"),
];

#[test]
fn canonical_table_round_trips_every_rem_team() {
    assert_eq!(CANONICAL_TEAMS, &EXPECTED);
    for (uid, color) in EXPECTED {
        assert_eq!(canonical_team_for_uid(uid), Some((uid, color)));
        assert_eq!(canonical_team_color_for_uid(uid), Some(color));
        assert_eq!(canonical_team_uid_for_color(color), Some(uid));
        assert!(is_canonical_team_uid(uid));
    }
}

#[test]
fn field_group_uids_are_exact_but_color_input_is_case_insensitive() {
    let blue = EXPECTED[2].0;
    for invalid in [
        "",
        "BLUE",
        "00000000000000000000000000000000",
        &blue.to_ascii_uppercase(),
        &format!(" {blue} "),
    ] {
        assert!(!is_canonical_team_uid(invalid));
        assert_eq!(canonical_team_color_for_uid(invalid), None);
    }
    assert_eq!(canonical_team_uid_for_color("  blue  "), Some(blue));
    assert_eq!(
        canonical_team_uid_for_color(" dark_blue "),
        Some(EXPECTED[7].0)
    );
    assert_eq!(canonical_team_uid_for_color("dark blue"), None);
    assert_eq!(canonical_team_uid_for_color(""), None);
}
