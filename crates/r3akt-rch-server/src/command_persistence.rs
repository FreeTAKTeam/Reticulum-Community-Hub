use super::{
    ApiError, AppState, HashMap, Instant, RchCore, RchSqliteStore, ZoneRecord,
    ensure_kill_switch_persistence_unlocked, record_sqlite_latency,
};

/// Reserve projection owners before `SQLite`, commit the domain command, then publish its delta.
/// HTTP marker/zone mutations use the same lock order, preventing a later cache write
/// from being overwritten by an older command snapshot. Rejected commands roll back.
#[cfg(test)]
pub(super) fn mutate<T>(
    state: &AppState,
    checklist: bool,
    operation: impl FnOnce(&mut RchCore) -> Result<(T, bool), ApiError>,
) -> Result<T, ApiError> {
    mutate_inner(state, checklist, Selection::Compatibility, operation)
}

pub(super) fn mutate_command<T>(
    state: &AppState,
    command: &super::MissionCommandEnvelope,
    checklist: bool,
    operation: impl FnOnce(&mut RchCore) -> Result<(T, bool), ApiError>,
) -> Result<T, ApiError> {
    mutate_inner(state, checklist, Selection::Scoped(command), operation)
}

enum Selection<'a> {
    Scoped(&'a super::MissionCommandEnvelope),
    #[cfg(test)]
    Compatibility,
}
fn mutate_inner<T>(
    state: &AppState,
    checklist: bool,
    command: Selection<'_>,
    operation: impl FnOnce(&mut RchCore) -> Result<(T, bool), ApiError>,
) -> Result<T, ApiError> {
    ensure_kill_switch_persistence_unlocked(state)?;
    let path = state
        .sqlite_path
        .as_ref()
        .ok_or_else(|| ApiError::ServiceUnavailable("RCH SQLite state unavailable".to_string()))?;
    let started = Instant::now();
    let mut markers = state
        .markers
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut zones = state
        .zones
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut store = RchSqliteStore::open(path.as_ref())
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut transaction = match command {
        Selection::Scoped(command) => store.begin_scoped_command(command, checklist),
        #[cfg(test)]
        Selection::Compatibility if checklist => store.begin_checklist_command(),
        #[cfg(test)]
        Selection::Compatibility => store.begin_r3akt_command(),
    }
    .map_err(|error| ApiError::Internal(error.to_string()))?;
    let (result, accepted) = operation(transaction.core_mut())?;
    if accepted {
        let delta = transaction
            .commit_delta()
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        super::message_residency::record_command(state, &delta);
        let after = delta.after;
        let before_markers = delta.before.markers;
        let before_zones = delta.before.zones;
        if !checklist {
            let mut prior_markers = before_markers
                .into_iter()
                .map(|record| (record.object_destination_hash.clone(), record))
                .collect::<HashMap<_, _>>();
            for record in after.markers {
                if prior_markers
                    .remove(&record.object_destination_hash)
                    .as_ref()
                    != Some(&record)
                {
                    markers.insert(record.object_destination_hash.clone(), record);
                }
            }
            for key in prior_markers.keys() {
                markers.remove(key);
            }
            let mut prior_zones = before_zones
                .into_iter()
                .map(|record| (record.zone_id.clone(), record))
                .collect::<HashMap<_, _>>();
            for record in after.zones {
                if prior_zones.remove(&record.zone_id).as_ref() != Some(&record) {
                    zones.insert(record.zone_id.clone(), ZoneRecord::from(record));
                }
            }
            for key in prior_zones.keys() {
                zones.remove(key);
            }
        }
    }
    record_sqlite_latency(state, started.elapsed());
    Ok(result)
}
