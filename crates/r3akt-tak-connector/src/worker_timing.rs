use std::time::Duration;

use super::{TAK_WORKER_MAX_BACKOFF, TakInboundPollReport, TakServiceDispatchReport};

pub(super) fn tak_worker_interval_after_report(
    current_interval: Duration,
    base_interval: Duration,
    report: &TakServiceDispatchReport,
) -> Duration {
    if report.error.is_some() {
        return current_interval
            .saturating_mul(2)
            .min(TAK_WORKER_MAX_BACKOFF);
    }
    base_interval
}

pub(super) fn tak_inbound_interval_after_report(
    current_interval: Duration,
    base_interval: Duration,
    report: &TakInboundPollReport,
) -> Duration {
    if report.error.is_some() {
        return current_interval
            .saturating_mul(2)
            .min(TAK_WORKER_MAX_BACKOFF);
    }
    base_interval
}
