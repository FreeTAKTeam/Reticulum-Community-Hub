//! Backend-owned marker symbol catalog.
//!
//! Symbol IDs are canonical keys shared by RCH and REM. Clients may render
//! them differently, but must not invent new keys.

use serde::Serialize;
use serde_json::Value;

/// Icon set a symbol's rendering hint belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SymbolSet {
    Mdi,
}

/// One catalog entry. Field order matches the RCH `/api/markers/symbols` shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct MarkerSymbol {
    pub id: &'static str,
    pub set: SymbolSet,
    pub mdi: Option<&'static str>,
    pub description: &'static str,
    pub tak: Option<&'static str>,
    pub category: &'static str,
}

const fn mdi(
    id: &'static str,
    icon: &'static str,
    description: &'static str,
    category: &'static str,
) -> MarkerSymbol {
    MarkerSymbol {
        id,
        set: SymbolSet::Mdi,
        mdi: Some(icon),
        description,
        tak: None,
        category,
    }
}

/// The supported symbols, in catalog order.
pub const CATALOG: &[MarkerSymbol] = &[
    mdi("marker", "map-marker", "Marker", "general"),
    mdi("friendly", "rectangle", "Friendly", "nato"),
    mdi("hostile", "rhombus", "Hostile", "nato"),
    mdi("neutral", "square", "Neutral", "nato"),
    mdi("unknown", "clover", "Unknown", "nato"),
    mdi("vehicle", "car", "Vehicle", "mobility"),
    mdi("drone", "drone", "Drone", "mobility"),
    mdi("animal", "paw", "Animal", "wildlife"),
    mdi("sensor", "radar", "Sensor", "equipment"),
    mdi("radio", "radio", "Radio", "equipment"),
    mdi("antenna", "antenna", "Antenna", "equipment"),
    mdi("camera", "camera", "Camera", "equipment"),
    mdi("fire", "fire", "Fire", "incident"),
    mdi("flood", "home-flood", "Flood", "incident"),
    mdi("person", "account", "Person", "people"),
    mdi("group", "account-group", "Group / Community", "people"),
    mdi(
        "infrastructure",
        "office-building",
        "Infrastructure",
        "infrastructure",
    ),
    mdi("medic", "hospital", "Medic", "medical"),
    mdi("alert", "alert", "Alert", "incident"),
    mdi("task", "clipboard-check", "Task", "task"),
];

/// Alternative spellings accepted on input and their canonical symbol IDs.
pub const ALIASES: &[(&str, &str)] = &[
    ("pin", "marker"),
    ("location", "marker"),
    ("car", "vehicle"),
    ("truck", "vehicle"),
    ("auto", "vehicle"),
    ("automobile", "vehicle"),
    ("uav", "drone"),
    ("uas", "drone"),
    ("wildlife", "animal"),
    ("pet", "animal"),
    ("radar", "sensor"),
    ("telemetry", "sensor"),
    ("vehicle-sensor", "sensor"),
    ("cctv", "camera"),
    ("flame", "fire"),
    ("wildfire", "fire"),
    ("water", "flood"),
    ("human", "person"),
    ("operator", "person"),
    ("community", "group"),
    ("group-community", "group"),
    ("team", "group"),
    ("building", "infrastructure"),
    ("facility", "infrastructure"),
    ("medical", "medic"),
    ("hospital", "medic"),
    ("alarm", "alert"),
    ("warning", "alert"),
    ("mission", "task"),
    ("assignment", "task"),
];

/// The catalog as the RCH `/api/markers/symbols` JSON array.
#[must_use]
pub fn catalog_json() -> Value {
    Value::Array(
        CATALOG
            .iter()
            .map(|symbol| serde_json::to_value(symbol).unwrap_or(Value::Null))
            .collect(),
    )
}

/// Whether `symbol` is a canonical catalog ID.
#[must_use]
pub fn is_supported(symbol: &str) -> bool {
    CATALOG.iter().any(|entry| entry.id == symbol)
}

/// Normalizes free-form input to a symbol key: lowercase, punctuation runs
/// collapsed to `-` within `.`-separated segments, then aliases resolved.
/// Returns `None` when nothing usable remains. The result may still be an
/// unsupported key; check it with [`is_supported`].
#[must_use]
pub fn normalize(symbol: &str) -> Option<String> {
    let normalized = symbol
        .trim()
        .to_lowercase()
        .split('.')
        .map(normalize_segment)
        .filter(|segment| !segment.is_empty())
        .collect::<Vec<_>>()
        .join(".");
    if normalized.is_empty() {
        return None;
    }
    let canonical = ALIASES
        .iter()
        .find(|(alias, _)| *alias == normalized)
        .map_or(normalized.as_str(), |(_, canonical)| canonical);
    Some(canonical.to_string())
}

fn normalize_segment(value: &str) -> String {
    let mut normalized = String::new();
    let mut pending_separator = false;
    for character in value.trim().chars().flat_map(char::to_lowercase) {
        if character.is_ascii_lowercase() || character.is_ascii_digit() {
            if pending_separator && !normalized.is_empty() {
                normalized.push('-');
            }
            normalized.push(character);
            pending_separator = false;
        } else {
            pending_separator = true;
        }
    }
    normalized
}
