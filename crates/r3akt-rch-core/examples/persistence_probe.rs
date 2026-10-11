//! Local residency/command-cost probe; Rust heap profiling uses an external harness.
use r3akt_profile_rch::{MissionCommandEnvelope, RchSource};
use r3akt_rch_core::{MessageRecord, RchSqliteStore};
use serde_json::json;
use std::time::Instant;

fn rss() -> Result<(u64, u64), Box<dyn std::error::Error>> {
    let status = std::fs::read_to_string("/proc/self/status")?;
    let number = |name: &str| -> Result<u64, Box<dyn std::error::Error>> {
        status
            .lines()
            .find(|line| line.starts_with(name))
            .and_then(|line| line.split_whitespace().nth(1))
            .ok_or_else(|| format!("missing {name}").into())
            .and_then(|value| Ok(value.parse()?))
    };
    Ok((number("VmRSS:")?, number("VmHWM:")?))
}
fn command(id: usize, kind: &str) -> MissionCommandEnvelope {
    MissionCommandEnvelope {
        command_id: format!("probe-{id}"),
        source: RchSource::new("probe"),
        timestamp: "2026-10-10T00:00:00Z".into(),
        command_type: kind.into(),
        args: json!({"uid":"probe-mission","mission_uid":"probe-mission","mission_name":"Probe","patch":{"mission_name":"Probe"}}),
        correlation_id: None,
        topics: vec![],
    }
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 2 {
        return Err("usage: persistence_probe <fixture-db> <iterations>".into());
    }
    let iterations = args[1].parse::<usize>()?;
    let mut store = RchSqliteStore::open(&args[0])?;
    let init = command(usize::MAX, "mission.registry.mission.upsert");
    let mut unit = store.begin_scoped_command(&init, false)?;
    unit.core_mut().handle_mission_sync_command(&init);
    unit.commit()?;
    let history = store.message_history_counts()?.0;
    let mut samples = Vec::new();
    let mut read_min = usize::MAX;
    let mut read_max = 0_usize;
    let mut bytes_max = 0_usize;
    let mut resident_max = 0_usize;
    let mut size_max = 0_usize;
    let started = Instant::now();
    for index in 0..iterations {
        let messages = store.recent_messages()?;
        resident_max = resident_max.max(messages.len());
        size_max = size_max.max(
            messages
                .iter()
                .map(MessageRecord::estimated_resident_bytes)
                .sum::<usize>(),
        );
        drop(messages);
        let request = command(index, "mission.registry.mission.patch");
        let mut unit = store.begin_scoped_command(&request, false)?;
        let response = unit.core_mut().handle_mission_sync_command(&request);
        if response.iter().any(|value| {
            value
                .results_field()
                .is_some_and(|v| v["status"] == "rejected")
        }) {
            return Err("probe command rejected".into());
        }
        let delta = unit.commit_delta()?;
        read_min = read_min.min(delta.rows_read);
        read_max = read_max.max(delta.rows_read);
        bytes_max = bytes_max.max(delta.payload_bytes_read);
        if index % 100 == 0 || index + 1 == iterations {
            samples.push(json!({"iteration":index,"rss_kib":rss()?.0}));
        }
    }
    let (resident, peak) = rss()?;
    println!(
        "{}",
        json!({"history":history,"iterations":iterations,"resident_count_max":resident_max,"resident_estimated_bytes_max":size_max,"command_rows_read_min":read_min,"command_rows_read_max":read_max,"command_payload_bytes_max":bytes_max,"rss_kib":resident,"peak_rss_kib":peak,"elapsed_ms":started.elapsed().as_millis(),"samples":samples})
    );
    // Deliberately retain the fixture for independent restart/history checks.
    Ok(())
}
