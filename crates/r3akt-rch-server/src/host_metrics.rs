//! Host CPU samples for the dashboard banner and chat traffic histograms.
//!
//! The sampler owns a short in-memory ring; traffic histograms are derived from
//! durable message history so they survive restarts.
use super::{
    ApiError, AppState, Arc, Duration, OutboundMessageRecord, RwLock, State, Value, VecDeque, json,
    normalized_delivery_state, unix_now_ms,
};
use axum::{Json, extract::Query};
use r3akt_rch_core::{MessageTrafficBucket, RchSqliteStore};
use serde::{Deserialize, Serialize};
use sysinfo::{Pid, ProcessRefreshKind, ProcessesToUpdate, System};

/// One sample every five seconds keeps ten minutes of history in 120 points.
pub const CPU_SAMPLE_INTERVAL: Duration = Duration::from_secs(5);
pub const CPU_SAMPLE_CAPACITY: usize = 120;

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct CpuSample {
    pub ts_ms: i64,
    /// Whole-machine CPU use, 0-100.
    pub system_percent: f32,
    /// This server process, normalised to the whole machine, 0-100.
    pub process_percent: Option<f32>,
}

pub type CpuSampleRing = Arc<RwLock<VecDeque<CpuSample>>>;

pub(crate) fn push_cpu_sample(ring: &CpuSampleRing, sample: CpuSample) -> Result<(), ApiError> {
    let mut samples = ring
        .write()
        .map_err(|error| ApiError::Internal(format!("cpu sample ring poisoned: {error}")))?;
    while samples.len() >= CPU_SAMPLE_CAPACITY {
        samples.pop_front();
    }
    samples.push_back(sample);
    Ok(())
}

struct CpuSampler {
    system: System,
    pid: Option<Pid>,
}

impl CpuSampler {
    fn new() -> Self {
        let pid = match sysinfo::get_current_pid() {
            Ok(pid) => Some(pid),
            Err(error) => {
                eprintln!("r3akt-rch-server cpu sampler: process CPU unavailable: {error}");
                None
            }
        };
        let mut system = System::new();
        system.refresh_cpu_usage();
        let mut sampler = Self { system, pid };
        sampler.refresh_process();
        sampler
    }

    fn refresh_process(&mut self) {
        if let Some(pid) = self.pid {
            self.system.refresh_processes_specifics(
                ProcessesToUpdate::Some(&[pid]),
                true,
                ProcessRefreshKind::nothing().with_cpu(),
            );
        }
    }

    fn sample(&mut self) -> CpuSample {
        self.system.refresh_cpu_usage();
        self.refresh_process();
        let cpu_count = self.system.cpus().len().max(1);
        let process_percent = self
            .pid
            .and_then(|pid| self.system.process(pid))
            .map(|process| process.cpu_usage() / cpu_count_f32(cpu_count));
        CpuSample {
            ts_ms: unix_now_ms(),
            system_percent: clamp_percent(self.system.global_cpu_usage()),
            process_percent: process_percent.map(clamp_percent),
        }
    }
}

fn cpu_count_f32(count: usize) -> f32 {
    u16::try_from(count).map_or(f32::from(u16::MAX), f32::from)
}

fn clamp_percent(value: f32) -> f32 {
    if value.is_finite() {
        value.clamp(0.0, 100.0)
    } else {
        0.0
    }
}

/// Sample machine and process CPU every [`CPU_SAMPLE_INTERVAL`] until runtime exit.
pub fn spawn_cpu_sampler(state: AppState) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut sampler = CpuSampler::new();
        let mut ticker = tokio::time::interval(CPU_SAMPLE_INTERVAL);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        // The first tick completes immediately; usage needs one interval of history.
        ticker.tick().await;
        loop {
            if !state.runtime_exit.until(ticker.tick()).await {
                break;
            }
            let sample = sampler.sample();
            if let Err(error) = push_cpu_sample(&state.cpu_samples, sample) {
                eprintln!("r3akt-rch-server cpu sampler stopped: {error}");
                break;
            }
        }
    })
}

pub(crate) async fn cpu_status(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let samples = state
        .cpu_samples
        .read()
        .map_err(|error| ApiError::Internal(format!("cpu sample ring poisoned: {error}")))?
        .iter()
        .copied()
        .collect::<Vec<_>>();
    Ok(Json(json!({
        "interval_seconds": CPU_SAMPLE_INTERVAL.as_secs(),
        "capacity": CPU_SAMPLE_CAPACITY,
        "samples": samples,
    })))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TrafficRange {
    Hour,
    Day,
    Week,
}

impl TrafficRange {
    fn parse(value: Option<&str>) -> Result<Self, ApiError> {
        match value.map(str::trim).filter(|value| !value.is_empty()) {
            None | Some("24h") => Ok(Self::Day),
            Some("1h") => Ok(Self::Hour),
            Some("7d") => Ok(Self::Week),
            Some(other) => Err(ApiError::BadRequest(format!(
                "range must be one of 1h, 24h, 7d (got {other})"
            ))),
        }
    }

    const fn label(self) -> &'static str {
        match self {
            Self::Hour => "1h",
            Self::Day => "24h",
            Self::Week => "7d",
        }
    }

    const fn bucket_ms(self) -> i64 {
        match self {
            Self::Hour => 60 * 1000,
            Self::Day => 15 * 60 * 1000,
            Self::Week => 60 * 60 * 1000,
        }
    }

    const fn bucket_count(self) -> usize {
        match self {
            Self::Hour => 60,
            Self::Day => 96,
            Self::Week => 168,
        }
    }

    /// Window ending at the close of the bucket that contains `now_ms`.
    fn window_start(self, now_ms: i64) -> i64 {
        let bucket_ms = self.bucket_ms();
        let end = now_ms.div_euclid(bucket_ms).saturating_add(1) * bucket_ms;
        let count = i64::try_from(self.bucket_count()).unwrap_or(i64::MAX);
        end.saturating_sub(count.saturating_mul(bucket_ms))
    }
}

#[derive(Debug, Default, Deserialize)]
pub(crate) struct TrafficQuery {
    range: Option<String>,
}

pub(crate) async fn chat_traffic(
    State(state): State<AppState>,
    Query(query): Query<TrafficQuery>,
) -> Result<Json<Value>, ApiError> {
    let range = TrafficRange::parse(query.range.as_deref())?;
    let start_ts_ms = range.window_start(unix_now_ms());
    let buckets = if let Some(path) = &state.sqlite_path {
        let path = path.clone();
        tokio::task::spawn_blocking(move || {
            RchSqliteStore::open_read_only(path.as_ref())
                .and_then(|store| {
                    store.message_traffic(start_ts_ms, range.bucket_ms(), range.bucket_count())
                })
                .map_err(|error| ApiError::Internal(format!("message traffic query: {error}")))
        })
        .await
        .map_err(|error| ApiError::Internal(format!("message traffic task: {error}")))??
    } else {
        let messages = state
            .messages
            .read()
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        resident_message_traffic(&messages, start_ts_ms, range)
    };
    Ok(Json(traffic_payload(range, start_ts_ms, &buckets)))
}

fn resident_message_traffic(
    messages: &[OutboundMessageRecord],
    start_ts_ms: i64,
    range: TrafficRange,
) -> Vec<MessageTrafficBucket> {
    let bucket_ms = range.bucket_ms();
    let mut buckets = vec![MessageTrafficBucket::default(); range.bucket_count()];
    for message in messages {
        let offset = message.created_ts_ms.saturating_sub(start_ts_ms);
        if offset < 0 {
            continue;
        }
        let Some(bucket) = usize::try_from(offset / bucket_ms)
            .ok()
            .and_then(|index| buckets.get_mut(index))
        else {
            continue;
        };
        let inbound = message
            .delivery_metadata
            .get("direction")
            .and_then(Value::as_str)
            == Some("inbound");
        if inbound {
            bucket.received += 1;
        } else {
            bucket.sent += 1;
            if normalized_delivery_state(message) == "failed" {
                bucket.failed += 1;
            }
        }
    }
    buckets
}

fn traffic_payload(
    range: TrafficRange,
    start_ts_ms: i64,
    buckets: &[MessageTrafficBucket],
) -> Value {
    let bucket_ms = range.bucket_ms();
    let mut totals = MessageTrafficBucket::default();
    let mut offset = start_ts_ms;
    let rows = buckets
        .iter()
        .map(|bucket| {
            totals.received = totals.received.saturating_add(bucket.received);
            totals.sent = totals.sent.saturating_add(bucket.sent);
            totals.failed = totals.failed.saturating_add(bucket.failed);
            let row = json!({
                "start_ts_ms": offset,
                "received": bucket.received,
                "sent": bucket.sent,
                "failed": bucket.failed,
            });
            offset = offset.saturating_add(bucket_ms);
            row
        })
        .collect::<Vec<_>>();
    json!({
        "range": range.label(),
        "bucket_seconds": bucket_ms / 1000,
        "start_ts_ms": start_ts_ms,
        "end_ts_ms": offset,
        "totals": totals,
        "buckets": rows,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(ts_ms: i64) -> CpuSample {
        CpuSample {
            ts_ms,
            system_percent: 12.5,
            process_percent: Some(1.0),
        }
    }

    #[test]
    fn cpu_ring_keeps_the_newest_samples() {
        let ring = CpuSampleRing::default();
        for ts in 0..i64::try_from(CPU_SAMPLE_CAPACITY + 5).unwrap() {
            push_cpu_sample(&ring, sample(ts)).unwrap();
        }
        let samples = ring.read().unwrap();
        assert_eq!(samples.len(), CPU_SAMPLE_CAPACITY);
        assert_eq!(samples.front().unwrap().ts_ms, 5);
        assert_eq!(
            samples.back().unwrap().ts_ms,
            i64::try_from(CPU_SAMPLE_CAPACITY + 4).unwrap()
        );
    }

    #[test]
    fn cpu_sampler_reports_percentages() {
        let mut sampler = CpuSampler::new();
        let value = sampler.sample();
        assert!((0.0..=100.0).contains(&value.system_percent));
        if let Some(process) = value.process_percent {
            assert!((0.0..=100.0).contains(&process));
        }
    }

    #[test]
    fn traffic_range_parsing_and_windows() {
        assert_eq!(TrafficRange::parse(None).unwrap(), TrafficRange::Day);
        assert_eq!(TrafficRange::parse(Some("1h")).unwrap(), TrafficRange::Hour);
        assert_eq!(TrafficRange::parse(Some("7d")).unwrap(), TrafficRange::Week);
        assert!(TrafficRange::parse(Some("2h")).is_err());
        // 10:07 rounds up to the 10:15 bucket close; 96 buckets back is 10:15 yesterday.
        let now = 10 * 3_600_000 + 7 * 60_000 + 86_400_000;
        assert_eq!(
            TrafficRange::Day.window_start(now),
            10 * 3_600_000 + 15 * 60_000
        );
    }

    #[test]
    fn resident_traffic_counts_directions_and_failures() {
        let message = |id: &str, ts: i64, inbound: bool, state: &str| OutboundMessageRecord {
            message_id: id.into(),
            topic_id: None,
            destination: None,
            sender: "hub".into(),
            content: String::new(),
            delivery_mode: r3akt_rch_core::DeliveryMode::Targeted,
            delivery_method: "direct".into(),
            delivery_policy_reason: String::new(),
            delivery_state: state.into(),
            delivery_metadata: if inbound {
                json!({"direction": "inbound"})
            } else {
                json!({})
            },
            created_ts_ms: ts,
            attachments: Vec::new(),
        };
        let start = 0;
        let messages = [
            message("a", 30_000, true, "delivered"),
            message("b", 61_000, false, "sent"),
            message("c", 62_000, false, "failed"),
            message("old", -1, false, "sent"),
            message("late", 3_600_000, false, "sent"),
        ];
        let buckets = resident_message_traffic(&messages, start, TrafficRange::Hour);
        assert_eq!(buckets[0].received, 1);
        assert_eq!(buckets[1].sent, 2);
        assert_eq!(buckets[1].failed, 1);
        let payload = traffic_payload(TrafficRange::Hour, start, &buckets);
        assert_eq!(payload["totals"]["sent"], 2);
        assert_eq!(payload["buckets"].as_array().unwrap().len(), 60);
        assert_eq!(payload["bucket_seconds"], 60);
    }

    async fn get_json(app: &axum::Router, uri: &str, key: Option<&str>) -> (u16, Value) {
        use http_body_util::BodyExt;
        use tower::ServiceExt;
        let mut request = axum::http::Request::builder().uri(uri);
        if let Some(key) = key {
            request = request.header("X-API-Key", key);
        }
        let response = app
            .clone()
            .oneshot(request.body(axum::body::Body::empty()).unwrap())
            .await
            .unwrap();
        let status = response.status().as_u16();
        let body = response.into_body().collect().await.unwrap().to_bytes();
        (status, serde_json::from_slice(&body).unwrap_or(Value::Null))
    }

    #[tokio::test]
    async fn dashboard_metric_routes_require_auth_and_report_json() {
        let state = AppState::default().with_api_key("secret");
        push_cpu_sample(&state.cpu_samples, sample(1)).unwrap();
        state.messages.write().unwrap().push(OutboundMessageRecord {
            message_id: "inbound".into(),
            topic_id: None,
            destination: None,
            sender: "peer".into(),
            content: "hi".into(),
            delivery_mode: r3akt_rch_core::DeliveryMode::Targeted,
            delivery_method: "direct".into(),
            delivery_policy_reason: String::new(),
            delivery_state: "delivered".into(),
            delivery_metadata: json!({"direction": "inbound"}),
            created_ts_ms: unix_now_ms(),
            attachments: Vec::new(),
        });
        let app = crate::create_app_with_state(state);

        let (status, _) = get_json(&app, "/Status/Cpu", None).await;
        assert_eq!(status, 401);

        let (status, cpu) = get_json(&app, "/Status/Cpu", Some("secret")).await;
        assert_eq!(status, 200);
        assert_eq!(cpu["interval_seconds"], 5);
        assert_eq!(cpu["samples"].as_array().unwrap().len(), 1);
        assert_eq!(cpu["samples"][0]["system_percent"], 12.5);

        let (status, traffic) = get_json(&app, "/Chat/Traffic?range=1h", Some("secret")).await;
        assert_eq!(status, 200);
        assert_eq!(traffic["range"], "1h");
        assert_eq!(
            traffic["totals"],
            json!({"received": 1, "sent": 0, "failed": 0})
        );
        assert_eq!(traffic["buckets"].as_array().unwrap().len(), 60);

        let (status, default_range) = get_json(&app, "/Chat/Traffic", Some("secret")).await;
        assert_eq!(status, 200);
        assert_eq!(default_range["range"], "24h");

        let (status, _) = get_json(&app, "/Chat/Traffic?range=2h", Some("secret")).await;
        assert_eq!(status, 400);
    }
}
