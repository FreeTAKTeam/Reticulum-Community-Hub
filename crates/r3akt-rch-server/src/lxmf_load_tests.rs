use std::collections::HashSet;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use r3akt_transport_rns::{
    LxmfMessageHistoryListRequest, LxmfSdkOutboundBatch, LxmfSdkOutboundBatchMessage,
    ReticulumdEventBatch, ReticulumdEventRecord, ZmqDataPlane,
};
use rand_core::OsRng;
use rns_core::identity::PrivateIdentity;
use serde_json::{Value, json};
use uuid::Uuid;

#[test]
#[ignore = "requires a local reticulumd mesh with ZeroMQ command endpoints"]
fn live_reticulumd_zmq_load_delivers_to_local_clients_when_configured() {
    let command_endpoints = match live_env_list("R3AKT_ZMQ_LOAD_COMMAND_ENDPOINTS") {
        Some(value) if value.len() >= 2 => value,
        _ => {
            eprintln!("skipping live ZeroMQ load test: R3AKT_ZMQ_LOAD_COMMAND_ENDPOINTS is unset");
            return;
        }
    };
    let mut destinations = match live_env_list("R3AKT_ZMQ_LOAD_DESTINATIONS") {
        Some(value) if value.len() == command_endpoints.len() => value,
        _ => {
            eprintln!("skipping live ZeroMQ load test: R3AKT_ZMQ_LOAD_DESTINATIONS is unset");
            return;
        }
    };
    let sender_response_endpoints = match live_env_list("R3AKT_ZMQ_LOAD_SENDER_RESPONSE_ENDPOINTS")
    {
        Some(value) if !value.is_empty() => value,
        _ => {
            eprintln!(
                "skipping live ZeroMQ load test: R3AKT_ZMQ_LOAD_SENDER_RESPONSE_ENDPOINTS is unset"
            );
            return;
        }
    };
    let receiver_response_endpoints = match live_env_list(
        "R3AKT_ZMQ_LOAD_RECEIVER_RESPONSE_ENDPOINTS",
    ) {
        Some(value) if !value.is_empty() => value,
        _ => {
            eprintln!(
                "skipping live ZeroMQ load test: R3AKT_ZMQ_LOAD_RECEIVER_RESPONSE_ENDPOINTS is unset"
            );
            return;
        }
    };

    let requested_messages = live_env_usize("R3AKT_ZMQ_LOAD_MESSAGES", 1_000).max(1);
    let sender_clients = live_env_usize("R3AKT_ZMQ_LOAD_SENDER_CLIENTS", 4)
        .max(1)
        .min(sender_response_endpoints.len());
    let receiver_count = live_env_usize("R3AKT_ZMQ_LOAD_RECEIVER_COUNT", 2)
        .max(1)
        .min(command_endpoints.len().saturating_sub(1))
        .min(receiver_response_endpoints.len());
    assert!(
        receiver_count > 0,
        "load test requires at least one receiver"
    );

    let poll_attempts = live_env_usize("R3AKT_ZMQ_LOAD_POLL_ATTEMPTS", 240);
    let poll_delay_ms = live_env_u64("R3AKT_ZMQ_LOAD_POLL_DELAY_MS", 250);
    let run_id = Uuid::new_v4().to_string();
    let expected_by_receiver =
        load_expected_content_by_receiver(&run_id, requested_messages, receiver_count);
    let received_progress = Arc::new(AtomicUsize::new(0));
    let poll_started = Instant::now();
    let mut receiver_threads = Vec::with_capacity(receiver_count);
    for receiver_index in 0..receiver_count {
        let data_plane = ZmqDataPlane::new(
            command_endpoints[receiver_index + 1].clone(),
            receiver_response_endpoints[receiver_index].clone(),
        )
        .expect("create persistent ZeroMQ load receiver");
        destinations[receiver_index + 1] = register_zmq_load_identity(
            &data_plane,
            PrivateIdentity::new_from_rand(OsRng)
                .to_private_key_bytes()
                .to_vec(),
            format!("RCH load receiver {}", receiver_index + 1),
        );
        let expected = expected_by_receiver[receiver_index].clone();
        let received_progress = Arc::clone(&received_progress);
        receiver_threads.push(thread::spawn(move || {
            poll_zmq_load_receiver(
                receiver_index,
                data_plane,
                expected,
                received_progress,
                poll_attempts,
                poll_delay_ms,
            )
        }));
    }
    thread::sleep(Duration::from_millis(250));

    let send_started = Instant::now();
    let mut accepted_count = 0usize;
    let mut first_send_error = None;
    let sender_private_key = PrivateIdentity::new_from_rand(OsRng)
        .to_private_key_bytes()
        .to_vec();
    let sender_data_planes = sender_response_endpoints
        .iter()
        .take(sender_clients)
        .map(|response_endpoint| {
            let data_plane =
                ZmqDataPlane::new(command_endpoints[0].clone(), response_endpoint.clone())
                    .expect("create persistent ZeroMQ load sender");
            let source = register_zmq_load_identity(
                &data_plane,
                sender_private_key.clone(),
                "RCH load sender".to_string(),
            );
            (Arc::new(data_plane), source)
        })
        .collect::<Vec<_>>();
    let wave_size = live_env_usize("R3AKT_ZMQ_LOAD_WAVE_SIZE", 800).clamp(1, 800);
    let wave_delay_ms = live_env_u64("R3AKT_ZMQ_LOAD_WAVE_DELAY_MS", 0);
    for wave_start in (0..requested_messages).step_by(wave_size) {
        let wave_end = wave_start.saturating_add(wave_size).min(requested_messages);
        let accepted_before_wave = accepted_count;
        let mut sender_threads = Vec::with_capacity(sender_clients);
        for (sender_index, (data_plane, source)) in sender_data_planes.iter().cloned().enumerate() {
            let destinations = destinations[1..=receiver_count].to_vec();
            let run_id = run_id.clone();
            sender_threads.push(thread::spawn(move || {
                send_zmq_load_messages(
                    sender_index,
                    sender_clients,
                    wave_start,
                    wave_end,
                    receiver_count,
                    data_plane,
                    source,
                    destinations,
                    run_id,
                )
            }));
        }
        for sender in sender_threads {
            let result = sender.join().expect("join ZeroMQ load sender");
            accepted_count = accepted_count.saturating_add(result.accepted);
            first_send_error = first_send_error.or(result.first_error);
        }
        println!(
            "live_zmq_load_wave phase=accepted range={wave_start}..{wave_end} accepted_total={accepted_count} received_total={}",
            received_progress.load(Ordering::Relaxed)
        );
        let expected_wave_acceptance = wave_end.saturating_sub(wave_start);
        let wave_acceptance = accepted_count.saturating_sub(accepted_before_wave);
        if wave_acceptance != expected_wave_acceptance {
            first_send_error.get_or_insert_with(|| {
                format!(
                    "wave {wave_start}..{wave_end} accepted {wave_acceptance}/{expected_wave_acceptance}"
                )
            });
            break;
        }
        let wave_deadline = Instant::now() + Duration::from_secs(60);
        while received_progress.load(Ordering::Relaxed) < accepted_count
            && Instant::now() < wave_deadline
        {
            thread::sleep(Duration::from_millis(25));
        }
        if received_progress.load(Ordering::Relaxed) < accepted_count {
            first_send_error.get_or_insert_with(|| {
                format!(
                    "receiver projection did not catch up after wave {wave_start}..{wave_end}: accepted={accepted_count} received={}",
                    received_progress.load(Ordering::Relaxed)
                )
            });
            break;
        }
        println!(
            "live_zmq_load_wave phase=received range={wave_start}..{wave_end} accepted_total={accepted_count} received_total={}",
            received_progress.load(Ordering::Relaxed)
        );
        if wave_delay_ms > 0 {
            thread::sleep(Duration::from_millis(wave_delay_ms));
        }
    }
    for (data_plane, _) in sender_data_planes {
        let _ = data_plane.shutdown();
    }
    let send_elapsed = send_started.elapsed();

    let mut receiver_results = Vec::with_capacity(receiver_count);
    for receiver in receiver_threads {
        receiver_results.push(receiver.join().expect("join ZeroMQ load receiver"));
    }
    let full_elapsed = poll_started.elapsed();
    let received_total = receiver_results
        .iter()
        .map(|result| result.received)
        .sum::<usize>();
    let per_client = receiver_results
        .iter()
        .map(|result| format!("client{}={}", result.receiver_index + 1, result.received))
        .collect::<Vec<_>>()
        .join(",");
    println!(
        "live_zmq_load_result status={} requested={} accepted={} received={} per_client={} send_elapsed_ms={} full_elapsed_ms={} send_messages_per_sec={:.1} e2e_messages_per_sec={:.1}",
        if accepted_count == requested_messages && received_total == requested_messages {
            "completed"
        } else {
            "incomplete"
        },
        requested_messages,
        accepted_count,
        received_total,
        per_client,
        send_elapsed.as_millis(),
        full_elapsed.as_millis(),
        messages_per_second(requested_messages, send_elapsed),
        messages_per_second(requested_messages, full_elapsed)
    );

    assert_eq!(
        accepted_count, requested_messages,
        "accepted send count mismatch; first error: {:?}",
        first_send_error
    );
    for result in &receiver_results {
        assert!(
            result.remaining_samples.is_empty(),
            "receiver {} missed {} messages; samples={:?}; last_error={:?}",
            result.receiver_index + 1,
            result.expected.saturating_sub(result.received),
            result.remaining_samples,
            result.last_error
        );
    }
    assert_eq!(received_total, requested_messages);
}

#[derive(Debug)]
struct ZmqLoadSendResult {
    accepted: usize,
    first_error: Option<String>,
}

#[derive(Debug)]
struct ZmqLoadReceiverResult {
    receiver_index: usize,
    expected: usize,
    received: usize,
    remaining_samples: Vec<String>,
    last_error: Option<String>,
}

fn live_env_list(name: &str) -> Option<Vec<String>> {
    std::env::var(name).ok().map(|value| {
        value
            .split([',', ';', '\n', '\r', '\t'])
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToString::to_string)
            .collect::<Vec<_>>()
    })
}

fn live_env_usize(name: &str, default: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(default)
}

fn live_env_u64(name: &str, default: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .unwrap_or(default)
}

fn messages_per_second(count: usize, elapsed: Duration) -> f64 {
    f64::from(u32::try_from(count).expect("message count fits in u32")) / elapsed.as_secs_f64()
}

fn load_content(run_id: &str, sequence: usize, receiver_index: usize) -> String {
    format!(
        "load-{run_id}-{sequence:05}-to-{}",
        receiver_index.saturating_add(1)
    )
}

fn load_expected_content_by_receiver(
    run_id: &str,
    requested_messages: usize,
    receiver_count: usize,
) -> Vec<HashSet<String>> {
    let mut expected = (0..receiver_count)
        .map(|_| HashSet::new())
        .collect::<Vec<_>>();
    for sequence in 0..requested_messages {
        let receiver_index = sequence % receiver_count;
        expected[receiver_index].insert(load_content(run_id, sequence, receiver_index));
    }
    expected
}

const ZMQ_LOAD_BATCH_CHUNK_SIZE: usize = 64;

#[allow(clippy::too_many_arguments)]
fn send_zmq_load_messages(
    sender_index: usize,
    sender_clients: usize,
    sequence_start: usize,
    sequence_end: usize,
    receiver_count: usize,
    data_plane: Arc<ZmqDataPlane>,
    source: String,
    destinations: Vec<String>,
    run_id: String,
) -> ZmqLoadSendResult {
    let mut accepted = 0usize;
    let mut first_error = None;
    let mut batch_index = sequence_start / ZMQ_LOAD_BATCH_CHUNK_SIZE;
    let batch_delay_ms = live_env_u64("R3AKT_ZMQ_LOAD_BATCH_DELAY_MS", 250);
    let mut pending = Vec::with_capacity(ZMQ_LOAD_BATCH_CHUNK_SIZE);
    for sequence in
        (sequence_start.saturating_add(sender_index)..sequence_end).step_by(sender_clients)
    {
        let receiver_index = sequence % receiver_count;
        let content = load_content(&run_id, sequence, receiver_index);
        pending.push(LxmfSdkOutboundBatchMessage {
            destination: destinations[receiver_index].clone(),
            title: "RCH load".to_string(),
            content,
            fields: json!({
                "load_run_id": run_id.clone(),
                "load_sequence": sequence,
                "load_receiver_index": receiver_index,
            }),
            delivery_method: Some("direct".to_string()),
            stamp_cost: None,
            include_ticket: None,
            try_propagation_on_fail: false,
            correlation_id: format!("load-{run_id}-{sequence:05}"),
        });
        if pending.len() >= ZMQ_LOAD_BATCH_CHUNK_SIZE {
            accepted = accepted.saturating_add(send_zmq_load_batch(
                data_plane.as_ref(),
                &mut first_error,
                source.as_str(),
                run_id.as_str(),
                sender_index,
                batch_index,
                std::mem::take(&mut pending),
            ));
            batch_index = batch_index.saturating_add(1);
            if batch_delay_ms > 0 {
                thread::sleep(Duration::from_millis(batch_delay_ms));
            }
        }
    }
    if !pending.is_empty() {
        accepted = accepted.saturating_add(send_zmq_load_batch(
            data_plane.as_ref(),
            &mut first_error,
            source.as_str(),
            run_id.as_str(),
            sender_index,
            batch_index,
            pending,
        ));
    }
    ZmqLoadSendResult {
        accepted,
        first_error,
    }
}

#[allow(clippy::too_many_arguments)]
fn send_zmq_load_batch(
    data_plane: &ZmqDataPlane,
    first_error: &mut Option<String>,
    source: &str,
    run_id: &str,
    sender_index: usize,
    batch_index: usize,
    messages: Vec<LxmfSdkOutboundBatchMessage>,
) -> usize {
    let message_count = messages.len();
    match data_plane.send_batch(LxmfSdkOutboundBatch {
        batch_id: format!("load-{run_id}-sender-{sender_index}-batch-{batch_index}"),
        source: source.to_string(),
        messages,
    }) {
        Ok(results) => {
            if let Some(rejected) = results.iter().find(|result| !result.accepted) {
                first_error.get_or_insert_with(|| {
                    format!(
                        "sender {sender_index} batch {batch_index} rejected id={} destination={} error={:?}",
                        rejected.id, rejected.destination, rejected.error
                    )
                });
            }
            results.iter().filter(|result| result.accepted).count()
        }
        Err(error) => {
            first_error.get_or_insert_with(|| {
                format!(
                    "sender {sender_index} batch {batch_index} ({message_count} messages): {error}"
                )
            });
            0
        }
    }
}

fn register_zmq_load_identity(
    data_plane: &ZmqDataPlane,
    private_key: Vec<u8>,
    display_name: String,
) -> String {
    // Each SDK session must prove ownership of its service identity before
    // sending from it or reading its inbound events and message history.
    data_plane
        .register_identity(crate::RchServiceIdentityConfig {
            private_key,
            display_name,
            capabilities: vec!["lxmf".to_string()],
            metadata: std::collections::BTreeMap::new(),
        })
        .expect("register ZeroMQ load service identity")
        .delivery_destination
        .expect("registered load identity has an LXMF delivery destination")
}

fn poll_zmq_load_receiver(
    receiver_index: usize,
    data_plane: ZmqDataPlane,
    mut expected: HashSet<String>,
    received_progress: Arc<AtomicUsize>,
    poll_attempts: usize,
    poll_delay_ms: u64,
) -> ZmqLoadReceiverResult {
    let expected_count = expected.len();
    let mut cursor = None;
    let mut last_error = None;
    for _ in 0..poll_attempts {
        match data_plane.poll_events(cursor.clone(), crate::RETICULUMD_EVENT_POLL_MAX) {
            Ok(batch) => {
                cursor = batch.next_cursor.clone();
                let received = remove_seen_load_messages(&mut expected, &batch);
                received_progress.fetch_add(received, Ordering::Relaxed);
                if received == 0 && !expected.is_empty() {
                    match recover_zmq_load_messages_from_history(&data_plane, &mut expected) {
                        Ok(recovered) => {
                            received_progress.fetch_add(recovered, Ordering::Relaxed);
                        }
                        Err(error) => last_error = Some(error),
                    }
                }
                if expected.is_empty() {
                    break;
                }
            }
            Err(error) => {
                let error = error.to_string();
                eprintln!(
                    "live_zmq_load_receiver_error receiver={} cursor={:?} error={error}",
                    receiver_index + 1,
                    cursor
                );
                last_error = Some(error);
                // Re-negotiate from the daemon's current retained event window.
                // Expected-message de-duplication makes replay safe and lets the
                // gate prove stream-gap recovery instead of stalling forever on
                // an expired cursor.
                cursor = None;
            }
        }
        thread::sleep(Duration::from_millis(poll_delay_ms));
    }
    let _ = data_plane.shutdown();
    let received = expected_count.saturating_sub(expected.len());
    let remaining_samples = expected.into_iter().take(5).collect::<Vec<_>>();
    ZmqLoadReceiverResult {
        receiver_index,
        expected: expected_count,
        received,
        remaining_samples,
        last_error,
    }
}

fn remove_seen_load_messages(
    expected: &mut HashSet<String>,
    batch: &ReticulumdEventBatch,
) -> usize {
    let mut removed = 0;
    for event in &batch.events {
        if !matches!(
            event.event_type.as_str(),
            "inbound" | "InboundMessageReceived"
        ) {
            continue;
        }
        if let Some(content) = load_event_content(event) {
            removed += usize::from(expected.remove(content));
        }
    }
    removed
}

fn recover_zmq_load_messages_from_history(
    data_plane: &ZmqDataPlane,
    expected: &mut HashSet<String>,
) -> Result<usize, String> {
    let request: LxmfMessageHistoryListRequest = serde_json::from_value(json!({
        "peer_id": null,
        "conversation_id": null,
        "include_receipts": false,
        "limit": 1000,
        "before_ts": null,
        "cursor": null
    }))
    .map_err(|error| error.to_string())?;
    let page = data_plane
        .message_history(request)
        .map_err(|error| error.to_string())?;
    let before = expected.len();
    for message in page.messages {
        expected.remove(message.content.as_str());
    }
    Ok(before.saturating_sub(expected.len()))
}

fn load_event_content(event: &ReticulumdEventRecord) -> Option<&str> {
    event
        .payload
        .get("message")
        .and_then(|message| message.get("content"))
        .and_then(Value::as_str)
        .or_else(|| event.payload.get("content").and_then(Value::as_str))
}
