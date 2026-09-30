use super::{
    ApiError, AppState, Arc, Duration, OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS,
    OUTBOUND_RETRY_WORKER_POLL_MS, OUTBOUND_RETRY_WORKER_TICK_TIMEOUT_MS,
    OutboundRetryWorkerReport, RETICULUMD_ANNOUNCE_IMPORT_LIMIT, RETICULUMD_ANNOUNCE_LIST_POLL_MS,
    RETICULUMD_EVENT_CURSOR_STREAM_CHECK_MS, RETICULUMD_INBOUND_WORKER_POLL_MS,
    RETICULUMD_LIST_MESSAGE_POLL_MS, ReticulumdEventPollTransport, ReticulumdEventWorkerReport,
    clear_reticulumd_event_cursor, import_reticulumd_announces_with_options,
    is_recoverable_reticulumd_event_cursor_error, json, load_reticulumd_event_cursor,
    lxmf_zmq_event_poll_enabled, outbound_error_is_rate_limited,
    process_lxmf_zmq_event_worker_tick, process_outbound_delivery_worker_tick,
    process_reticulumd_event_worker_tick_with_options, process_reticulumd_list_message_worker_tick,
    record_outbound_retry_worker_report, record_reticulumd_inbound_worker_announce_error,
    record_reticulumd_inbound_worker_event_cursor_reset,
    record_reticulumd_inbound_worker_event_error, record_system_event_best_effort,
    runtime_shutdown_requested, select_reticulumd_event_poll_transport,
    set_outbound_retry_worker_running, set_reticulumd_inbound_worker_running,
};

pub fn spawn_outbound_delivery_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    spawn_outbound_delivery_worker_with_interval(
        state,
        Duration::from_millis(OUTBOUND_RETRY_WORKER_POLL_MS),
    )
}

pub fn spawn_outbound_delivery_worker_with_interval(
    state: AppState,
    poll_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    spawn_outbound_with_tick(
        state,
        poll_interval,
        Duration::from_millis(OUTBOUND_RETRY_WORKER_TICK_TIMEOUT_MS),
        process_outbound_delivery_worker_tick,
    )
}

pub(super) fn spawn_outbound_with_tick<F>(
    state: AppState,
    poll_interval: Duration,
    tick_timeout: Duration,
    tick: F,
) -> tokio::task::JoinHandle<()>
where
    F: Fn(&AppState) -> Result<OutboundRetryWorkerReport, ApiError> + Send + Sync + 'static,
{
    let tick = Arc::new(tick);
    tokio::spawn(async move {
        let poll_interval = poll_interval.max(Duration::from_millis(10));
        set_outbound_retry_worker_running(&state, false, poll_interval);
        loop {
            if state.runtime_exit.is_requested() {
                break;
            }
            if runtime_shutdown_requested(&state) {
                set_outbound_retry_worker_running(&state, false, poll_interval);
                state.runtime_exit.sleep(poll_interval).await;
                continue;
            }
            set_outbound_retry_worker_running(&state, true, poll_interval);
            let worker_state = state.clone();
            let tick = Arc::clone(&tick);
            let mut worker_task = tokio::task::spawn_blocking(move || tick(&worker_state));
            // A timeout does not cancel spawn_blocking. Retain and join the same
            // task before another tick or SDK/daemon cleanup can begin.
            let outcome = if let Ok(result) =
                tokio::time::timeout(tick_timeout, &mut worker_task).await
            {
                result
            } else {
                record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(
                        "outbound retry worker tick timed out; waiting for active work".to_string(),
                    ),
                );
                worker_task.await
            };
            match outcome {
                Ok(Ok(_report)) => {}
                Ok(Err(error)) => record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(error.to_string()),
                ),
                Err(error) => record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(error.to_string()),
                ),
            }
            state.runtime_exit.sleep(poll_interval).await;
        }
        set_outbound_retry_worker_running(&state, false, poll_interval);
    })
}

pub fn spawn_reticulumd_inbound_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    spawn_reticulumd_inbound_worker_with_interval(
        state,
        Duration::from_millis(RETICULUMD_INBOUND_WORKER_POLL_MS),
    )
}

pub fn spawn_reticulumd_inbound_worker_with_interval(
    state: AppState,
    poll_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let poll_interval = poll_interval.max(Duration::from_millis(50));
        let announce_list_poll_interval = Duration::from_millis(RETICULUMD_ANNOUNCE_LIST_POLL_MS);
        set_reticulumd_inbound_worker_running(&state, false, poll_interval);
        let endpoint = state
            .reticulumd_rpc_endpoint
            .as_deref()
            .map(ToOwned::to_owned);
        let zmq_event_poll_enabled = lxmf_zmq_event_poll_enabled();
        let zmq_command_endpoint = zmq_event_poll_enabled
            .then(|| {
                state
                    .lxmf_zmq_command_endpoint
                    .as_deref()
                    .map(ToOwned::to_owned)
            })
            .flatten();
        let zmq_response_endpoint = zmq_event_poll_enabled
            .then(|| {
                state
                    .lxmf_zmq_response_endpoint
                    .as_deref()
                    .map(ToOwned::to_owned)
            })
            .flatten();
        let event_poll_transport = select_reticulumd_event_poll_transport(
            endpoint.as_deref(),
            zmq_command_endpoint.as_deref(),
            zmq_response_endpoint.as_deref(),
            zmq_event_poll_enabled,
        );
        if event_poll_transport == ReticulumdEventPollTransport::None {
            return;
        }
        let rpc_projection_fallback = event_poll_transport == ReticulumdEventPollTransport::Rpc;
        let Some(source) = state.reticulumd_source.as_deref().map(ToOwned::to_owned) else {
            return;
        };
        let mut cursor = load_reticulumd_event_cursor(&state);
        let mut last_list_message_poll: Option<std::time::Instant> = None;
        let mut last_announce_list_poll: Option<std::time::Instant> = None;
        let mut last_cursor_stream_check: Option<std::time::Instant> = None;
        let mut rate_limit_cooldown_until: Option<std::time::Instant> = None;
        loop {
            if state.runtime_exit.is_requested() {
                break;
            }
            if runtime_shutdown_requested(&state) {
                set_reticulumd_inbound_worker_running(&state, false, poll_interval);
                state.runtime_exit.sleep(poll_interval).await;
                continue;
            }
            set_reticulumd_inbound_worker_running(&state, true, poll_interval);
            if let Some(cooldown_until) = rate_limit_cooldown_until {
                let now = std::time::Instant::now();
                if cooldown_until > now {
                    state
                        .runtime_exit
                        .sleep((cooldown_until - now).min(poll_interval))
                        .await;
                    continue;
                }
                rate_limit_cooldown_until = None;
            }
            let worker_state = state.clone();
            let worker_endpoint = endpoint.clone();
            let worker_zmq_command_endpoint = zmq_command_endpoint.clone();
            let worker_zmq_response_endpoint = zmq_response_endpoint.clone();
            let worker_source = source.clone();
            let worker_cursor = cursor.clone();
            let worker_event_poll_transport = event_poll_transport;
            let check_cursor_stream_position = worker_event_poll_transport
                == ReticulumdEventPollTransport::Rpc
                && cursor.is_some()
                && last_cursor_stream_check.is_none_or(|last_check| {
                    last_check.elapsed()
                        >= Duration::from_millis(RETICULUMD_EVENT_CURSOR_STREAM_CHECK_MS)
                });
            if check_cursor_stream_position {
                last_cursor_stream_check = Some(std::time::Instant::now());
            }
            let mut event_poll_ok = false;
            match tokio::task::spawn_blocking(move || match worker_event_poll_transport {
                ReticulumdEventPollTransport::Rpc => {
                    let Some(worker_endpoint) = worker_endpoint else {
                        return Ok(ReticulumdEventWorkerReport { next_cursor: None });
                    };
                    process_reticulumd_event_worker_tick_with_options(
                        &worker_state,
                        worker_endpoint.as_str(),
                        worker_source.as_str(),
                        worker_cursor,
                        check_cursor_stream_position,
                    )
                }
                ReticulumdEventPollTransport::Zmq => {
                    let (Some(command_endpoint), Some(response_endpoint)) =
                        (worker_zmq_command_endpoint, worker_zmq_response_endpoint)
                    else {
                        return Ok(ReticulumdEventWorkerReport { next_cursor: None });
                    };
                    process_lxmf_zmq_event_worker_tick(
                        &worker_state,
                        command_endpoint.as_str(),
                        response_endpoint.as_str(),
                        worker_source.as_str(),
                        worker_cursor,
                    )
                }
                ReticulumdEventPollTransport::None => {
                    Ok(ReticulumdEventWorkerReport { next_cursor: None })
                }
            })
            .await
            {
                Ok(Ok(report)) => {
                    cursor = report.next_cursor;
                    event_poll_ok = true;
                }
                Ok(Err(error)) => {
                    let error = error.to_string();
                    record_reticulumd_inbound_worker_event_error(&state, error.clone());
                    if outbound_error_is_rate_limited(&error) {
                        rate_limit_cooldown_until = Some(
                            std::time::Instant::now()
                                + Duration::from_millis(
                                    OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS as u64,
                                ),
                        );
                        state.runtime_exit.sleep(poll_interval).await;
                        continue;
                    }
                    if is_recoverable_reticulumd_event_cursor_error(&error) {
                        cursor = None;
                        let reset_reason = match clear_reticulumd_event_cursor(&state) {
                            Ok(()) => error,
                            Err(reset_error) => {
                                format!("{error}; failed to clear persisted cursor: {reset_error}")
                            }
                        };
                        record_reticulumd_inbound_worker_event_cursor_reset(&state, reset_reason);
                    }
                }
                Err(error) => {
                    record_reticulumd_inbound_worker_event_error(&state, error.to_string());
                }
            }
            if state.runtime_exit.is_requested() {
                break;
            }
            let should_poll_list_messages = last_list_message_poll.is_none_or(|last_poll| {
                last_poll.elapsed() >= Duration::from_millis(RETICULUMD_LIST_MESSAGE_POLL_MS)
            });
            if should_poll_list_messages
                && endpoint.is_some()
                && rpc_projection_fallback
                && !state.runtime_exit.is_requested()
            {
                last_list_message_poll = Some(std::time::Instant::now());
                let worker_state = state.clone();
                let worker_endpoint = endpoint.clone().unwrap_or_default();
                let worker_source = source.clone();
                match tokio::task::spawn_blocking(move || {
                    process_reticulumd_list_message_worker_tick(
                        &worker_state,
                        worker_endpoint.as_str(),
                        worker_source.as_str(),
                    )
                })
                .await
                {
                    Ok(Ok(_)) => {}
                    Ok(Err(error)) => {
                        let error = error.to_string();
                        record_reticulumd_inbound_worker_event_error(&state, error.clone());
                        if outbound_error_is_rate_limited(&error) {
                            rate_limit_cooldown_until = Some(
                                std::time::Instant::now()
                                    + Duration::from_millis(
                                        OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS as u64,
                                    ),
                            );
                            state.runtime_exit.sleep(poll_interval).await;
                            continue;
                        }
                    }
                    Err(error) => {
                        let error = error.to_string();
                        record_reticulumd_inbound_worker_event_error(&state, error.clone());
                        if outbound_error_is_rate_limited(&error) {
                            rate_limit_cooldown_until = Some(
                                std::time::Instant::now()
                                    + Duration::from_millis(
                                        OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS as u64,
                                    ),
                            );
                            state.runtime_exit.sleep(poll_interval).await;
                            continue;
                        }
                    }
                }
            }
            let should_poll_announces = event_poll_ok
                && last_announce_list_poll
                    .is_none_or(|last_poll| last_poll.elapsed() >= announce_list_poll_interval);
            if should_poll_announces
                && endpoint.is_some()
                && rpc_projection_fallback
                && !state.runtime_exit.is_requested()
            {
                last_announce_list_poll = Some(std::time::Instant::now());
                let worker_state = state.clone();
                let worker_endpoint = endpoint.clone().unwrap_or_default();
                match tokio::task::spawn_blocking(move || {
                    import_reticulumd_announces_with_options(
                        &worker_state,
                        worker_endpoint.as_str(),
                        RETICULUMD_ANNOUNCE_IMPORT_LIMIT,
                        false,
                    )
                })
                .await
                {
                    Ok(Ok(_)) => {}
                    Ok(Err(error)) => {
                        let error = error.to_string();
                        record_system_event_best_effort(
                            &state,
                            "reticulumd_announce_import_error",
                            "Reticulumd announce list import failed",
                            json!({
                                "operation": "list_announces",
                                "exception_type": "ApiError",
                                "exception_message": error,
                            }),
                        );
                        if outbound_error_is_rate_limited(&error) {
                            rate_limit_cooldown_until = Some(
                                std::time::Instant::now()
                                    + Duration::from_millis(
                                        OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS as u64,
                                    ),
                            );
                            state.runtime_exit.sleep(poll_interval).await;
                            continue;
                        }
                    }
                    Err(error) => {
                        let error = error.to_string();
                        record_reticulumd_inbound_worker_announce_error(&state, error.clone());
                        if outbound_error_is_rate_limited(&error) {
                            rate_limit_cooldown_until = Some(
                                std::time::Instant::now()
                                    + Duration::from_millis(
                                        OUTBOUND_RATE_LIMIT_RETRY_BACKOFF_MS as u64,
                                    ),
                            );
                            state.runtime_exit.sleep(poll_interval).await;
                            continue;
                        }
                    }
                }
            }
            state.runtime_exit.sleep(poll_interval).await;
        }
        set_reticulumd_inbound_worker_running(&state, false, poll_interval);
    })
}
