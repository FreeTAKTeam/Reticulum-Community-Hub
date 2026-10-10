//! Mission relationships revisited during read-set dependency closure.
use super::{HashSet, RchCoreError, ReadSet};

impl ReadSet<'_> {
    #[allow(clippy::too_many_lines)]
    pub(super) fn mission_dependencies(
        &mut self,
        kind: &str,
        target_missions: &HashSet<String>,
        expand: bool,
        expansions: &HashSet<String>,
    ) -> Result<(), RchCoreError> {
        let r = self;
        for entry in r.snapshot.log_entries.clone() {
            select!(
                r,
                missions,
                "rch_missions",
                "uid",
                Some(entry.mission_uid.as_str())
            );
        }
        for change in r.snapshot.mission_changes.clone() {
            select!(
                r,
                missions,
                "rch_missions",
                "uid",
                Some(change.mission_uid.as_str())
            );
        }
        for mission in r.snapshot.missions.clone() {
            select!(
                r,
                missions,
                "rch_missions",
                "uid",
                mission.parent_uid.as_deref()
            );
            if kind.starts_with("mission.registry.mission.")
                && target_missions.contains(&mission.uid)
            {
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "parent_uid",
                    Some(mission.uid.as_str())
                );
                select!(
                    r,
                    mission_zone_links,
                    "rch_mission_zone_links",
                    "mission_uid",
                    Some(mission.uid.as_str())
                );
                select!(
                    r,
                    mission_marker_links,
                    "rch_mission_marker_links",
                    "mission_uid",
                    Some(mission.uid.as_str())
                );
            }
            if expand && target_missions.contains(&mission.uid) {
                if expansions.contains("teams")
                    || expansions.contains("team_members")
                    || expansions.contains("assets")
                {
                    select!(
                        r,
                        mission_team_links,
                        "rch_mission_team_links",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                    select!(
                        r,
                        teams,
                        "rch_teams",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                }
                if expansions.contains("checklists") {
                    select!(
                        r,
                        checklists,
                        "rch_checklists",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                }
                if expansions.contains("mission_changes") {
                    select!(
                        r,
                        mission_changes,
                        "rch_mission_changes",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                }
                if expansions.contains("log_entries") {
                    select!(
                        r,
                        log_entries,
                        "rch_log_entries",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                }
                if expansions.contains("assignments") {
                    select!(
                        r,
                        assignments,
                        "rch_assignments",
                        "mission_uid",
                        Some(mission.uid.as_str())
                    );
                }
                if expansions.contains("topic") {
                    select!(
                        r,
                        topics,
                        "rch_topics",
                        "topic_id",
                        mission.topic_id.as_deref()
                    );
                    select!(
                        r,
                        subscribers,
                        "rch_subscribers",
                        "topic_id",
                        mission.topic_id.as_deref()
                    );
                }
            }
        }
        Ok(())
    }
}
