use std::collections::{HashMap, HashSet};

use serde_json::{Value, json};

use super::{
    IdentityAnnounceRecord, RECENT_ANNOUNCE_WINDOW_MS, RchCore, millis_to_rfc3339, normalize_hash,
    utc_now_ms,
};

impl RchCore {
    fn identity_announce_has_rem_capabilities(record: &IdentityAnnounceRecord) -> bool {
        let capabilities: HashSet<_> = record
            .announce_capabilities
            .iter()
            .map(String::as_str)
            .collect();
        capabilities.contains("r3akt") && capabilities.contains("emergencymessages")
    }

    pub(super) fn identity_has_rem_announce_capabilities(&self, identity: &str) -> bool {
        self.identity_announce_for_identity(identity)
            .is_some_and(Self::identity_announce_has_rem_capabilities)
    }

    fn identity_announce_for_identity(&self, identity: &str) -> Option<&IdentityAnnounceRecord> {
        let identity = normalize_hash(Some(identity))?;
        if let Some(record) = self.identity_announces.get(&identity) {
            return Some(record);
        }
        self.identity_announces
            .values()
            .filter(|record| {
                record
                    .announced_identity_hash
                    .as_deref()
                    .is_some_and(|announced| announced == identity)
            })
            .max_by_key(|record| {
                (
                    record.source_interface.as_deref() == Some("identity"),
                    record.display_name.is_some(),
                    record.last_seen_ts_ms,
                )
            })
    }

    fn canonical_identity_for_rem_source(&self, source: &str) -> Option<String> {
        let source = normalize_hash(Some(source))?;
        self.identity_announce_for_identity(&source)
            .and_then(|record| {
                record
                    .announced_identity_hash
                    .as_deref()
                    .and_then(|identity| normalize_hash(Some(identity)))
            })
            .or(Some(source))
    }

    pub(super) fn shared_team_uids_for_rem_source(&self, source: &str) -> HashSet<String> {
        let Some(identity) = self.canonical_identity_for_rem_source(source) else {
            return HashSet::new();
        };
        self.team_members
            .values()
            .filter(|member| {
                normalize_hash(Some(&member.rns_identity)).as_deref() == Some(identity.as_str())
                    || member.client_identities.iter().any(|client_identity| {
                        normalize_hash(Some(client_identity)).as_deref() == Some(identity.as_str())
                    })
                    || self
                        .team_member_client_links
                        .contains(&(member.uid.clone(), identity.clone()))
            })
            .filter_map(|member| member.team_uid.clone())
            .collect()
    }

    fn team_member_identities_for_teams(&self, team_uids: &HashSet<String>) -> HashSet<String> {
        let mut identities = HashSet::new();
        for member in self.team_members.values().filter(|member| {
            member
                .team_uid
                .as_ref()
                .is_some_and(|team_uid| team_uids.contains(team_uid))
        }) {
            if let Some(identity) = normalize_hash(Some(&member.rns_identity)) {
                identities.insert(identity);
            }
            identities.extend(
                member
                    .client_identities
                    .iter()
                    .filter_map(|identity| normalize_hash(Some(identity))),
            );
            identities.extend(
                self.team_member_client_links
                    .iter()
                    .filter(|(member_uid, _)| member_uid == &member.uid)
                    .filter_map(|(_, identity)| normalize_hash(Some(identity))),
            );
        }
        identities
    }

    pub(super) fn rem_team_peer_registry_payload(&self, source: &str) -> Value {
        let team_uids = self.shared_team_uids_for_rem_source(source);
        let team_identities = self.team_member_identities_for_teams(&team_uids);
        let requester_identity = self.canonical_identity_for_rem_source(source);
        let requester_destination = normalize_hash(Some(source));
        let cutoff_ms = utc_now_ms().saturating_sub(RECENT_ANNOUNCE_WINDOW_MS);
        let rem_modes: HashMap<String, String> = self
            .identity_rem_modes
            .iter()
            .map(|(identity, record)| {
                let mode = record.mode.trim().to_ascii_lowercase();
                (
                    identity.clone(),
                    if mode.is_empty() {
                        "autonomous".to_string()
                    } else {
                        mode
                    },
                )
            })
            .collect();
        let mut candidates: HashMap<String, (&IdentityAnnounceRecord, String)> = HashMap::new();
        for record in self.identity_announces.values() {
            let identity = record
                .announced_identity_hash
                .as_deref()
                .and_then(|value| normalize_hash(Some(value)))
                .or_else(|| normalize_hash(Some(&record.destination_hash)));
            let Some(identity) = identity else {
                continue;
            };
            if !team_identities.contains(&identity)
                || requester_identity.as_deref() == Some(identity.as_str())
                || requester_destination.as_deref()
                    == normalize_hash(Some(&record.destination_hash)).as_deref()
                || record.last_seen_ts_ms < cutoff_ms
                || !record.client_type.trim().eq_ignore_ascii_case("rem")
                || !Self::identity_announce_has_rem_capabilities(record)
            {
                continue;
            }
            if self
                .identity_states
                .get(&identity)
                .is_some_and(|state| state.is_banned || state.is_blackholed)
            {
                continue;
            }
            let source = record
                .source_interface
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map_or_else(|| "identity".to_string(), str::to_ascii_lowercase);
            let replace = candidates
                .get(&identity)
                .is_none_or(|(_, existing_source)| {
                    source == "destination" && existing_source != "destination"
                });
            if replace {
                candidates.insert(identity, (record, source));
            }
        }

        let effective_connected_mode = candidates.iter().any(|(identity, (record, _))| {
            rem_modes
                .get(identity)
                .or_else(|| {
                    normalize_hash(Some(&record.destination_hash))
                        .as_ref()
                        .and_then(|destination| rem_modes.get(destination))
                })
                .is_some_and(|mode| mode == "connected")
        });
        let mut items = candidates
            .into_iter()
            .map(|(identity, (record, source))| {
                let destination_hash = if source == "destination" {
                    normalize_hash(Some(&record.destination_hash))
                        .unwrap_or_else(|| identity.clone())
                } else {
                    identity.clone()
                };
                json!({
                    "identity": identity.clone(),
                    "destination_hash": destination_hash,
                    "display_name": record
                        .display_name
                        .as_deref()
                        .map(str::trim)
                        .filter(|value| !value.is_empty()),
                    "announce_capabilities": record.announce_capabilities.clone(),
                    "client_type": record.client_type.trim().to_ascii_lowercase(),
                    "registered_mode": rem_modes
                        .get(&identity)
                        .or_else(|| {
                            normalize_hash(Some(&record.destination_hash))
                                .as_ref()
                                .and_then(|destination| rem_modes.get(destination))
                        })
                        .cloned()
                        .unwrap_or_else(|| "autonomous".to_string()),
                    "last_seen": millis_to_rfc3339(record.last_seen_ts_ms),
                    "status": "active",
                })
            })
            .collect::<Vec<_>>();
        items.sort_by(|left, right| {
            left["identity"]
                .as_str()
                .unwrap_or_default()
                .cmp(right["identity"].as_str().unwrap_or_default())
        });

        json!({
            "scope": "shared_teams",
            "effective_connected_mode": effective_connected_mode,
            "items": items,
        })
    }
}
