//! Canonical REM color teams used by RCH field-group routing.

/// Canonical `(UID, color)` pairs. UIDs are lowercase and colors uppercase.
pub const CANONICAL_TEAMS: &[(&str, &str)] = &[
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

/// Looks up an exact, lowercase wire UID and returns its canonical pair.
#[must_use]
pub fn canonical_team_for_uid(team_uid: &str) -> Option<(&'static str, &'static str)> {
    CANONICAL_TEAMS
        .iter()
        .copied()
        .find(|(uid, _)| *uid == team_uid)
}

/// Looks up the color for an exact, lowercase wire UID.
#[must_use]
pub fn canonical_team_color_for_uid(team_uid: &str) -> Option<&'static str> {
    canonical_team_for_uid(team_uid).map(|(_, color)| color)
}

/// Looks up a color case-insensitively after trimming surrounding whitespace.
#[must_use]
pub fn canonical_team_uid_for_color(color: &str) -> Option<&'static str> {
    CANONICAL_TEAMS
        .iter()
        .find(|(_, candidate)| candidate.eq_ignore_ascii_case(color.trim()))
        .map(|(uid, _)| *uid)
}

/// Checks the exact wire UID without trimming or changing its case.
#[must_use]
pub fn is_canonical_team_uid(team_uid: &str) -> bool {
    canonical_team_for_uid(team_uid).is_some()
}
