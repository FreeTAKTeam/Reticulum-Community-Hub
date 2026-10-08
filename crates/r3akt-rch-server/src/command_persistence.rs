use super::{
    ApiError, AppState, HashMap, Instant, MarkerRecord, RchCore, RchSqliteStore, ZoneRecord,
    ensure_kill_switch_persistence_unlocked, record_sqlite_latency,
};

/// Reserve projection owners before `SQLite`, commit the domain command, then publish its delta.
/// HTTP marker/zone mutations use the same lock order, preventing a later cache write
/// from being overwritten by an older command snapshot. Rejected commands roll back.
pub(super) fn mutate<T>(
    state: &AppState,
    checklist: bool,
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
    let mut transaction = if checklist {
        store.begin_checklist_command()
    } else {
        store.begin_r3akt_command()
    }
    .map_err(|error| ApiError::Internal(error.to_string()))?;
    // Cache publication only compares these two projections. Cloning the
    // complete core here duplicated announce/domain history before every
    // command, including checklist commands that never publish either cache.
    let before_markers = if checklist {
        Vec::new()
    } else {
        transaction.core_mut().markers()
    };
    let before_zones = if checklist {
        Vec::new()
    } else {
        transaction.core_mut().zones()
    };
    let (result, accepted) = operation(transaction.core_mut())?;
    if accepted {
        let after = transaction
            .commit()
            .map_err(|error| ApiError::Internal(error.to_string()))?;
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
                    markers.insert(
                        record.object_destination_hash.clone(),
                        MarkerRecord::from(record),
                    );
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
