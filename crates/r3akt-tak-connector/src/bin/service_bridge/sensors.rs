//! Canonical marker association is resolved by the existing bridge before sensor import.
use super::{RchNorthboundClient, SeenEntries, TakCotSender, TakService, Value, json};
use r3akt_map_core::sensor::{OriginPosition, SensorState};
use r3akt_tak_connector::{CotSensorObservation, SensorCotSnapshot};

pub(super) fn import(
    client: &RchNorthboundClient,
    id: &str,
    payload: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    let Some(value) = payload.get("_r3s_sensor") else {
        return Ok(());
    };
    let observation: CotSensorObservation = serde_json::from_value(value.clone())?;
    let position = observation.position;
    client.post_json_idempotent("/Sensors",&json!({"originId":id,"position":position,"sensor":observation.sensor,"staleAtMs":observation.stale_at_ms,"manifest":observation.manifest}),&format!("cot-sensor:{id}:{}",position.fix_at_ms))?;
    Ok(())
}
pub(super) fn export<S: TakCotSender>(
    client: &RchNorthboundClient,
    service: &mut TakService<S>,
    seen: &mut SeenEntries,
) -> Result<(), Box<dyn std::error::Error>> {
    let Some(snapshot) = client.get_optional_json("/Sensors")? else {
        return Ok(());
    };
    let ttl = snapshot["ttlMs"]
        .as_u64()
        .ok_or("missing native sensor TTL")?;
    for origin in snapshot["items"]
        .as_array()
        .ok_or("invalid sensor projection")?
    {
        // Stock ATAK has one sensor per parent: choose the first ID in native sorted order.
        let Some(sensor) = origin["sensors"].as_array().and_then(|s| s.first()) else {
            continue;
        };
        if sensor["display"]["stale"] != false
            || sensor["display"]["positionStale"] != false
            || sensor["display"]["unsynchronized"] != false
        {
            continue;
        }
        let position: OriginPosition = serde_json::from_value(origin["position"].clone())?;
        let state: SensorState = serde_json::from_value(sensor["state"].clone())?;
        let id = origin["originId"]
            .as_str()
            .ok_or("missing sensor origin identity")?;
        let expires_at = state
            .sample_at_ms
            .saturating_add(ttl)
            .min(sensor["sourceExpiresAtMs"].as_u64().unwrap_or(u64::MAX));
        let cot = SensorCotSnapshot {
            origin_id: id.into(),
            origin_kind: origin["originKind"].as_str().unwrap_or("mobile").into(),
            manifest: if sensor["manifest"].is_null() {
                None
            } else {
                Some(serde_json::from_value(sensor["manifest"].clone())?)
            },
            label: origin["label"].as_str().unwrap_or(id).into(),
            position,
            sensor: state,
            stale_at_ms: expires_at,
        };
        let revision = serde_json::to_vec(&(
            &cot.label,
            &cot.origin_kind,
            &cot.manifest,
            &cot.position,
            &cot.sensor,
            cot.stale_at_ms,
        ))?;
        let key = format!(
            "sensor:{id}:{:x}",
            <sha2::Sha256 as sha2::Digest>::digest(revision)
        );
        if seen.contains(&key) {
            continue;
        }
        service.queue_sensor(&cot)?;
        seen.insert(key);
    }
    Ok(())
}
