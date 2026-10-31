//! Native sensor projection and explicit operator/TAK updates through the existing authenticated API.
use super::{
    ApiError, AppState, Deserialize, Json, RchSqliteStore, State, Value,
    ensure_kill_switch_persistence_unlocked, json, unix_now_ms,
};
const DEFAULT_TTL_MS: u64 = 300_000;
pub(crate) fn openapi() -> Value {
    json!({
        "get":{"summary":"Native R3S origin/sensor projections with source freshness and display geometry.",
            "responses":{"200":{"description":"Snapshot; geometry and freshness are computed by the native runtime.","content":{"application/json":{"schema":{"type":"object","required":["items","observedAtMs","ttlMs"],"properties":{"items":{"type":"array","items":{"type":"object"}},"observedAtMs":{"type":"integer"},"ttlMs":{"type":"integer"}}}}}}}},
        "post":{"summary":"Explicit operator/TAK update of a sensor on an existing canonical marker.",
            "description":"Uses source milliseconds, immutable writer ownership, nullable altitude/datum, and checked R3S/1 sensor fields. See docs/r3s-telemetry.md for the complete contract. Requires the configured northbound credential.",
            "requestBody":{"required":true,"content":{"application/json":{"schema":{"type":"object","additionalProperties":false,"required":["originId","position","sensor"],"properties":{"originId":{"type":"string","pattern":"^[0-9a-f]{32}$"},"position":{"type":"object","required":["lat","lon","fixAtMs","altitudeDatum"]},"sensor":{"type":"object","required":["sensorId","sampleAtMs","rangeKind"]},"staleAtMs":{"type":["integer","null"]},"manifest":{"type":["object","null"]}}}}}},
            "responses":{"200":{"description":"Accepted current state or idempotent older source revision."},"400":{"description":"Invalid schema, source revision, origin association or writer."},"401":{"description":"Northbound authentication required."}}
        }
    })
}
pub(crate) async fn list(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let path = state
        .sqlite_path
        .as_ref()
        .ok_or_else(|| ApiError::ServiceUnavailable("sensor persistence requires SQLite".into()))?;
    let mut store = RchSqliteStore::open(path.as_ref())
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    let ttl = store
        .setting_values(["sensor_telemetry_ttl_ms"])
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?[0]
        .as_deref()
        .map(str::parse::<u64>)
        .transpose()
        .map_err(|e| ApiError::Internal(e.to_string()))?
        .unwrap_or(DEFAULT_TTL_MS)
        .clamp(1000, 86_400_000);
    let now = u64::try_from(unix_now_ms()).map_err(|e| ApiError::Internal(e.to_string()))?;
    let items = store
        .sensor_origins()
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?
        .iter()
        .map(|o| o.projection(now, ttl))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    Ok(Json(json!({"items":items,"observedAtMs":now,"ttlMs":ttl})))
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct OperatorSensorUpdate {
    origin_id: String,
    position: r3akt_map_core::sensor::OriginPosition,
    sensor: r3akt_map_core::sensor::SensorState,
    stale_at_ms: Option<u64>,
    manifest: Option<r3akt_map_core::sensor::SensorManifest>,
}
pub(crate) async fn update(
    State(state): State<AppState>,
    Json(input): Json<OperatorSensorUpdate>,
) -> Result<Json<Value>, ApiError> {
    let _gate = state
        .broker_work_gate
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    ensure_kill_switch_persistence_unlocked(&state)?;
    let path = state
        .sqlite_path
        .as_ref()
        .ok_or_else(|| ApiError::ServiceUnavailable("sensor persistence requires SQLite".into()))?;
    let source = state.reticulumd_source.as_deref().ok_or_else(|| {
        ApiError::ServiceUnavailable("sensor writer requires configured RCH destination".into())
    })?;
    let mut markers = state
        .markers
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut store = RchSqliteStore::open(path.as_ref())
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    let mut unit = store
        .begin_r3akt_command()
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    unit.stage_operator_sensor(
        source,
        &input.origin_id,
        &input.position,
        &input.sensor,
        input.stale_at_ms,
        u64::try_from(unix_now_ms()).map_err(|e| ApiError::Internal(e.to_string()))?,
    )
    .map_err(|e| ApiError::BadRequest(e.to_string()))?;
    if let Some(manifest) = &input.manifest {
        unit.stage_operator_sensor_manifest(
            source,
            &input.origin_id,
            manifest,
            input.sensor.sample_at_ms,
            u64::try_from(unix_now_ms()).map_err(|e| ApiError::Internal(e.to_string()))?,
        )
        .map_err(|e| ApiError::BadRequest(e.to_string()))?;
    }
    let delta = unit
        .commit_delta()
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    for before in &delta.before.markers {
        markers.remove(&before.object_destination_hash);
    }
    for after in delta.after.markers {
        markers.insert(after.object_destination_hash.clone(), after);
    }
    drop(markers);
    Ok(Json(json!({"accepted":true,"originId":input.origin_id})))
}
