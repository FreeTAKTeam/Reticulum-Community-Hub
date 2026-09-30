use super::{
    ApiError, AppState, Duration, LOCAL_TELEMETRY_SAMPLER_INTERVAL_MS, TelemetryRecord,
    iso8601_from_unix_ms, json, record_system_event_best_effort, runtime_shutdown_requested,
    unix_now_ms,
};

pub fn spawn_rch_identity_announce_worker(
    state: AppState,
    announce_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        if announce_interval.is_zero() {
            return;
        }
        let mut ticker = tokio::time::interval(announce_interval);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        // Registration performs the initial announce; the first periodic tick
        // therefore starts after a complete configured interval.
        ticker.tick().await;
        loop {
            if !state.runtime_exit.until(ticker.tick()).await {
                break;
            }
            if runtime_shutdown_requested(&state) {
                continue;
            }
            let Some(data_plane) = state.lxmf_zmq_data_plane.clone() else {
                return;
            };
            match tokio::task::spawn_blocking(move || data_plane.announce_identity()).await {
                Ok(Ok(_)) => {}
                Ok(Err(error)) => {
                    record_system_event_best_effort(
                        &state,
                        "identity_announce_error",
                        "Periodic RCH identity announce failed",
                        json!({
                            "operation": "sdk_identity_announce_now_v2",
                            "exception_type": "TransportError",
                            "exception_message": error.to_string(),
                        }),
                    );
                }
                Err(error) => {
                    record_system_event_best_effort(
                        &state,
                        "identity_announce_error",
                        "Periodic RCH identity announce task failed",
                        json!({
                            "operation": "sdk_identity_announce_now_v2",
                            "exception_type": "JoinError",
                            "exception_message": error.to_string(),
                        }),
                    );
                }
            }
        }
    })
}

pub fn spawn_local_telemetry_sampler(
    state: AppState,
    peer_destination: impl Into<String>,
) -> tokio::task::JoinHandle<()> {
    spawn_local_telemetry_sampler_with_interval(
        state,
        peer_destination,
        Duration::from_millis(LOCAL_TELEMETRY_SAMPLER_INTERVAL_MS),
    )
}

pub fn spawn_local_telemetry_sampler_with_interval(
    state: AppState,
    peer_destination: impl Into<String>,
    interval: Duration,
) -> tokio::task::JoinHandle<()> {
    let peer_destination = peer_destination.into();
    tokio::spawn(async move {
        if interval.is_zero() {
            return;
        }
        let mut ticker = tokio::time::interval(interval.max(Duration::from_millis(10)));
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        loop {
            if !state.runtime_exit.until(ticker.tick()).await {
                break;
            }
            if runtime_shutdown_requested(&state) {
                continue;
            }
            if let Err(error) = record_local_time_telemetry(&state, &peer_destination) {
                record_system_event_best_effort(
                    &state,
                    "telemetry_error",
                    "Local telemetry sampler failed to record a snapshot",
                    json!({
                        "operation": "local_sampler",
                        "exception_type": "ApiError",
                        "exception_message": error.to_string(),
                    }),
                );
            }
        }
    })
}

pub(super) fn record_local_time_telemetry(
    state: &AppState,
    peer_destination: &str,
) -> Result<TelemetryRecord, ApiError> {
    let now_ms = unix_now_ms();
    let timestamp_s = now_ms / 1000;
    state.record_telemetry(
        peer_destination,
        json!({
            "time": {
                "timestamp": timestamp_s,
                "iso": iso8601_from_unix_ms(now_ms),
            }
        }),
        timestamp_s,
        None,
    )
}
