//! One marker representation for RCH and REM, with Sideband-compatible objects.
//! Field 3 identifies the object independently of the LXMF sender. Field 13
//! retains the full R3AKT replica and deletion semantics. Routing stays outside
//! this codec. The standard stream has no deletion/tombstone operation.

use serde::{Serialize, Serializer, ser::SerializeMap};
use serde_json::{Value, json};

use crate::{MarkerRecord, marker, replica, symbols, telemetry_encode};

struct Binary(Vec<u8>);
impl Serialize for Binary {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_bytes(&self.0)
    }
}

/// Standard packed Telemeter for a stationary marker. Name and notes are
/// carried in the Information sensor; the marker's source time is preserved.
///
/// # Errors
/// Rejects invalid markers, timestamps or sensor readings.
pub fn packed_telemeter(marker: &MarkerRecord) -> Result<Vec<u8>, String> {
    replica::from_api_value(&marker.api_value(), marker.local_id.clone())
        .map_err(|error| error.to_string())?;
    let seconds =
        u64::try_from(marker.updated_ts_ms).map_err(|_| "invalid marker timestamp")? / 1000;
    let information = marker.notes.as_ref().map_or_else(
        || marker.name.clone(),
        |notes| format!("{}\n{notes}", marker.name),
    );
    telemetry_encode::encode_with_information(
        seconds,
        Some(telemetry_encode::Location {
            latitude: marker.lat,
            longitude: marker.lon,
            altitude: 0.0,
            speed: 0.0,
            bearing: 0.0,
            accuracy: 0.0,
            updated_at_s: seconds,
        }),
        None,
        Some(&information),
    )
    .map_err(str::to_string)
}

/// Encode a complete LXMF fields map. Optional application commands are
/// retained in field 9 for existing REM/RCH command processing.
///
/// # Errors
/// Rejects unknown marker events or invalid marker records.
pub fn encode_fields(
    event_type: &str,
    marker: &MarkerRecord,
    source: &str,
    commands: Option<&Value>,
) -> Result<Vec<u8>, String> {
    let deleted = event_type == replica::DELETE_EVENT;
    if !deleted && !replica::UPSERT_EVENTS.contains(&event_type) {
        return Err("unsupported marker event".into());
    }
    let hash = marker::object_destination_hash(&marker.object_destination_hash)
        .map_err(|error| error.to_string())?;
    let hash = (0..hash.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hash[index..index + 2], 16))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| error.to_string())?;
    let stream = if deleted {
        None
    } else {
        let icon = symbols::CATALOG
            .iter()
            .find(|entry| entry.id == marker.symbol)
            .and_then(|entry| entry.mdi)
            .unwrap_or("map-marker");
        Some(vec![(
            Binary(hash),
            marker.updated_ts_ms / 1000,
            Binary(packed_telemeter(marker)?),
            (icon, Binary(vec![255, 255, 255]), Binary(vec![48, 96, 160])),
        )])
    };
    let event = json!({
        "event_type": event_type,
        "payload": marker.api_value(),
        "source": { "rns_identity": source },
    });
    let mut bytes = Vec::new();
    let mut serializer = rmp_serde::Serializer::new(&mut bytes);
    let mut fields = (&mut serializer)
        .serialize_map(Some(
            1 + usize::from(stream.is_some()) + usize::from(commands.is_some()),
        ))
        .map_err(|error| error.to_string())?;
    if let Some(stream) = stream {
        fields
            .serialize_entry(&3_u8, &stream)
            .map_err(|error| error.to_string())?;
    }
    if let Some(commands) = commands {
        fields
            .serialize_entry(&9_u8, commands)
            .map_err(|error| error.to_string())?;
    }
    fields
        .serialize_entry(&13_u8, &event)
        .map_err(|error| error.to_string())?;
    fields.end().map_err(|error| error.to_string())?;
    Ok(bytes)
}
