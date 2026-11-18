//! MECP emergency message decoding (`MECP/<severity>/<codes>/<details>`).
use serde::{Deserialize, Serialize};

use crate::RchProfileError;

const MECP_PREFIX: &str = "MECP/";

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct MecpCoordinates {
    pub latitude: f64,
    pub longitude: f64,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct MecpDecodedExtras {
    pub callsign: Option<String>,
    pub eta_minutes: Option<u16>,
    pub language: Option<String>,
    pub pax: Option<u16>,
    pub references: Vec<String>,
    pub coordinates: Option<MecpCoordinates>,
    pub timestamp: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DecodedMecpCode {
    pub code: String,
    pub category: String,
    pub label: String,
    pub known: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DecodedMecpMessage {
    pub valid: bool,
    pub severity: Option<u8>,
    pub codes: Vec<String>,
    pub category: Option<String>,
    pub details: String,
    pub raw: String,
    pub byte_length: usize,
    pub code_details: Vec<DecodedMecpCode>,
    pub extras: MecpDecodedExtras,
    pub warnings: Vec<String>,
}

#[must_use]
pub fn mecp_category_label(category: &str) -> &str {
    match category {
        "M" => "Medical",
        "T" => "Terrain / Infrastructure",
        "W" => "Weather / Environment",
        "S" => "Supplies",
        "P" => "Position / Movement",
        "C" => "Coordination",
        "R" => "Response",
        "D" => "Drill / Test",
        "L" => "Life / Leisure",
        "X" => "Threat / Security",
        "H" => "Have / Offer Resources",
        "B" => "Beacon",
        _ => "MECP",
    }
}

#[must_use]
pub fn mecp_severity_label(severity: u8) -> &'static str {
    match severity {
        0 => "Mayday",
        1 => "Urgent",
        2 => "Safety",
        3 => "Routine",
        _ => "Unknown",
    }
}

#[must_use]
pub fn mecp_severity_status(severity: u8) -> &'static str {
    match severity {
        0 => "red",
        1 => "yellow",
        2 => "green",
        _ => "unknown",
    }
}

#[must_use]
#[allow(clippy::too_many_lines)]
pub fn mecp_event_label(code: &str) -> Option<&'static str> {
    Some(match code {
        "M01" => "Injury",
        "M02" => "Unconscious person",
        "M03" => "Breathing difficulty",
        "M04" => "Cardiac event",
        "M05" => "Hypothermia",
        "M06" => "Severe bleeding",
        "M07" => "Fracture / immobile",
        "M08" => "Burns",
        "M09" => "Multiple casualties",
        "M10" => "Deceased",
        "M11" => "Animal bite / sting",
        "M12" => "Allergic reaction / anaphylaxis",
        "M13" => "Poisoning / toxic exposure",
        "M14" => "Persons located alive",
        "M15" => "Area searched, no victims found",
        "T01" => "Road blocked",
        "T02" => "Bridge out",
        "T03" => "Building collapsed",
        "T04" => "Flooding",
        "T05" => "Landslide",
        "T06" => "Power out",
        "T07" => "Fire",
        "T08" => "Avalanche",
        "T09" => "Path impassable",
        "T10" => "Shelter available",
        "T11" => "Drowning / water rescue needed",
        "T12" => "Water contamination",
        "T13" => "Earthquake",
        "T14" => "Gas leak",
        "T15" => "Chemical spill / HAZMAT",
        "T16" => "Vehicle accident",
        "T17" => "Vehicle fire",
        "W01" => "Storm approaching",
        "W02" => "Visibility zero",
        "W03" => "Extreme cold",
        "W04" => "Extreme heat",
        "W05" => "Air quality danger",
        "W06" => "Tsunami / tidal surge warning",
        "S01" => "Need water",
        "S02" => "Need food",
        "S03" => "Need medication",
        "S04" => "Need battery / power",
        "S05" => "Need fuel",
        "S06" => "Need tools / equipment",
        "P01" => "Stranded / stuck",
        "P02" => "Evacuating toward",
        "P03" => "Sheltering in place",
        "P04" => "En route to",
        "P05" => "At GPS coordinates",
        "P06" => "Lost",
        "P07" => "Group separated",
        "C01" => "Send rescue",
        "C02" => "Need transport",
        "C03" => "Relay this message",
        "C04" => "Confirm received",
        "C05" => "How many people",
        "C06" => "What is status",
        "C07" => "Can you reach",
        "C08" => "Rendezvous at",
        "R01" => "Acknowledged",
        "R02" => "Help coming",
        "R03" => "ETA [minutes]",
        "R04" => "Cannot assist",
        "R05" => "Redirecting to",
        "R06" => "Stand by",
        "R07" => "Situation resolved / all clear",
        "D01" => "This is a drill",
        "D02" => "This is a test",
        "D03" => "End of drill",
        "D04" => "Ignore previous - sent in error",
        "L01" => "Beer / drinks",
        "L02" => "Coffee",
        "L03" => "Food ready",
        "L04" => "Summit reached",
        "L05" => "At camp",
        "L06" => "Running late",
        "L07" => "Good signal here",
        "L08" => "Photo opportunity",
        "L09" => "Wildlife spotted",
        "L10" => "Beautiful view",
        "L11" => "Trail conditions good",
        "L12" => "Trail conditions bad",
        "L13" => "Need a break",
        "L14" => "Heading home",
        "L15" => "Good morning / check-in",
        "L16" => "Good night",
        "L17" => "Thank you",
        "L18" => "Having fun",
        "L19" => "Festival / event here",
        "L20" => "Node test / ping",
        "X01" => "Dangerous person / threat nearby",
        "X02" => "Area unsafe - avoid",
        "X03" => "Gunfire / explosions heard",
        "X04" => "Civil unrest / crowd danger",
        "X05" => "Theft / looting reported",
        "X06" => "Authorities / emergency services present",
        "X07" => "Checkpoint / road closure",
        "H01" => "Have water available",
        "H02" => "Have food available",
        "H03" => "Have medical supplies",
        "H04" => "Have power / charging",
        "H05" => "Have fuel",
        "H06" => "Have tools / equipment",
        "H07" => "Have shelter / space for [N]pax",
        "H08" => "Have transport / vehicle",
        "B01" => "Automated distress beacon active",
        "B02" => "Beacon acknowledged",
        "B03" => "Cancel beacon - I am OK",
        _ => return None,
    })
}

#[must_use]
pub fn is_mecp_category_code(value: &str) -> bool {
    matches!(
        value,
        "M" | "T" | "W" | "S" | "P" | "C" | "R" | "D" | "L" | "X" | "H" | "B"
    )
}

fn invalid_mecp_message(raw: &str, warnings: Vec<String>) -> DecodedMecpMessage {
    DecodedMecpMessage {
        valid: false,
        severity: None,
        codes: Vec::new(),
        category: None,
        details: String::new(),
        raw: raw.to_string(),
        byte_length: raw.len(),
        code_details: Vec::new(),
        extras: MecpDecodedExtras::default(),
        warnings,
    }
}

fn is_mecp_code(token: &str) -> bool {
    let bytes = token.as_bytes();
    bytes.len() == 3
        && bytes[0].is_ascii_uppercase()
        && bytes[1].is_ascii_digit()
        && bytes[2].is_ascii_digit()
}

fn parse_token_u16_prefix(token: &str, suffix: &str) -> Option<u16> {
    token
        .strip_suffix(suffix)
        .or_else(|| token.strip_suffix(&suffix.to_ascii_uppercase()))
        .and_then(|value| value.parse::<u16>().ok())
}

/// Decode the compact REM MECP event body while preserving the original text payload.
#[allow(clippy::too_many_lines)]
pub fn decode_mecp_message(input: &str) -> Result<DecodedMecpMessage, RchProfileError> {
    let raw = input.trim();
    if !raw.starts_with(MECP_PREFIX) {
        return Ok(invalid_mecp_message(raw, Vec::new()));
    }

    let severity = raw
        .as_bytes()
        .get(5)
        .and_then(|value| char::from(*value).to_digit(10))
        .and_then(|value| u8::try_from(value).ok());
    let Some(severity) = severity.filter(|value| (0..=3).contains(value)) else {
        return Ok(invalid_mecp_message(
            raw,
            vec!["Invalid MECP severity or separator.".to_string()],
        ));
    };
    if raw.as_bytes().get(6) != Some(&b'/') {
        return Ok(invalid_mecp_message(
            raw,
            vec!["Invalid MECP severity or separator.".to_string()],
        ));
    }

    let tokens = raw[7..]
        .split_whitespace()
        .filter(|token| !token.is_empty())
        .collect::<Vec<_>>();
    let mut codes = Vec::new();
    let mut details_start = tokens.len();
    for (index, token) in tokens.iter().enumerate() {
        let code = token.to_ascii_uppercase();
        if !is_mecp_code(&code) {
            details_start = index;
            break;
        }
        codes.push(code);
    }
    if codes.is_empty() {
        return Ok(invalid_mecp_message(
            raw,
            vec!["MECP message does not contain an event code.".to_string()],
        ));
    }

    let mut code_details = Vec::new();
    let mut warnings = Vec::new();
    for code in &codes {
        let category = code[0..1].to_string();
        if !is_mecp_category_code(&category) {
            return Ok(invalid_mecp_message(
                raw,
                vec![format!("Invalid MECP category \"{category}\".")],
            ));
        }
        let label = mecp_event_label(code);
        if label.is_none() {
            warnings.push(format!("Unknown MECP event code \"{code}\"."));
        }
        code_details.push(DecodedMecpCode {
            code: code.clone(),
            category,
            label: label.unwrap_or(code).to_string(),
            known: label.is_some(),
        });
    }

    let mut extras = MecpDecodedExtras::default();
    let mut eta_consumed = false;
    for token in &tokens[details_start..] {
        if let Some(value) = token.strip_prefix('~').filter(|value| !value.is_empty()) {
            extras.callsign = Some(value.to_string());
            continue;
        }
        if let Some(value) = token.strip_prefix('#').filter(|value| !value.is_empty()) {
            extras.references.push(format!("#{value}"));
            continue;
        }
        if let Some(value) = token.strip_prefix('@') {
            if value.len() == 4 && value.chars().all(|item| item.is_ascii_digit()) {
                extras.timestamp = Some(value.to_string());
            } else if (2..=3).contains(&value.len())
                && value.chars().all(|item| item.is_ascii_alphabetic())
            {
                extras.language = Some(value.to_ascii_lowercase());
            }
            continue;
        }
        if let Some(value) = parse_token_u16_prefix(&token.to_ascii_lowercase(), "pax") {
            extras.pax = Some(value);
            continue;
        }
        if let Some((latitude, longitude)) = token.split_once(',')
            && let (Ok(latitude), Ok(longitude)) =
                (latitude.parse::<f64>(), longitude.parse::<f64>())
        {
            if (-90.0..=90.0).contains(&latitude) && (-180.0..=180.0).contains(&longitude) {
                extras.coordinates = Some(MecpCoordinates {
                    latitude,
                    longitude,
                });
            } else {
                warnings.push(format!("Coordinates outside valid range: \"{token}\"."));
            }
            continue;
        }
        if !eta_consumed && codes.iter().any(|code| code == "R03") {
            let lower = token.to_ascii_lowercase();
            let eta = lower
                .parse::<u16>()
                .ok()
                .or_else(|| parse_token_u16_prefix(&lower, "m"))
                .or_else(|| parse_token_u16_prefix(&lower, "min"));
            if let Some(eta) = eta {
                extras.eta_minutes = Some(eta);
                eta_consumed = true;
            }
        }
    }

    Ok(DecodedMecpMessage {
        valid: true,
        severity: Some(severity),
        codes,
        category: code_details.first().map(|code| code.category.clone()),
        details: tokens[details_start..].join(" "),
        raw: raw.to_string(),
        byte_length: raw.len(),
        code_details,
        extras,
        warnings,
    })
}
