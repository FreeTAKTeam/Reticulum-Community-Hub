//! Bounded identity directory HTTP adapter. `SQLite` owns eligibility and ordering.
use super::{
    ApiError, AppState, ClientListQuery, IdentityDirectoryConfig, IdentityStatusRecord,
    client_should_appear_in_client_list, iso8601_from_unix_ms, legacy_identity_payload,
    merge_identity_payload_client_display_metadata, normalize_identity_key,
    openapi_paginated_list_operation, rem_annotations_from_records, resolve_python_pagination,
    unix_now_ms,
};
use axum::Json;
use r3akt_rch_core::RchSqliteStore;
use r3akt_rch_core::{IdentityDirectoryClientOverlay, IdentityDirectoryQuery};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Default, Deserialize)]
pub(super) struct IdentityListQuery {
    pub page: Option<i64>,
    pub per_page: Option<i64>,
    pub view: Option<String>,
    pub search: Option<String>,
    pub identity: Option<String>,
    pub client_type: Option<String>,
    pub order: Option<String>,
}

impl IdentityListQuery {
    fn has_filters(&self) -> bool {
        self.view.is_some()
            || self.search.is_some()
            || self.identity.is_some()
            || self.client_type.is_some()
            || self.order.is_some()
    }
    fn resolve(
        &self,
        config: &IdentityDirectoryConfig,
    ) -> Result<IdentityDirectoryQuery, ApiError> {
        let recent_cutoff_ms = match self.view.as_deref().unwrap_or("all") {
            "all" => None,
            "recent" => Some(unix_now_ms().saturating_sub(config.recent_hours * 3_600_000)),
            _ => return Err(ApiError::Unprocessable("view must be recent or all".into())),
        };
        let newest_first = match self.order.as_deref().unwrap_or("identity_asc") {
            "identity_asc" => false,
            "last_seen_desc" => true,
            _ => {
                return Err(ApiError::Unprocessable(
                    "order must be last_seen_desc or identity_asc".into(),
                ));
            }
        };
        let client_type = match self.client_type.as_deref() {
            None | Some("all") => None,
            Some("rem" | "generic_lxmf") => self.client_type.clone(),
            _ => {
                return Err(ApiError::Unprocessable(
                    "client_type must be all, rem or generic_lxmf".into(),
                ));
            }
        };
        let identity = self
            .identity
            .as_deref()
            .map(|value| {
                normalize_identity_key(value)
                    .ok_or_else(|| ApiError::Unprocessable("identity must not be empty".into()))
            })
            .transpose()?;
        let (offset, limit) = self
            .pagination()?
            .map_or((0, i64::MAX as usize), |(page, size)| {
                (page.saturating_sub(1).saturating_mul(size), size)
            });
        Ok(IdentityDirectoryQuery {
            search: self.search.clone(),
            identity,
            client_type,
            recent_cutoff_ms,
            newest_first,
            offset,
            limit,
        })
    }
    fn pagination(&self) -> Result<Option<(usize, usize)>, ApiError> {
        if self.page.is_none() && self.per_page.is_none() {
            return Ok(None);
        }
        resolve_python_pagination(self.page, self.per_page).map(Some)
    }
}

pub(super) fn list(state: &AppState, query: &IdentityListQuery) -> Result<Json<Value>, ApiError> {
    let resolved = query.resolve(&state.identity_directory_config)?;
    // Preserve the explicit legacy array and in-memory test/runtime contract.
    // New clients always opt into SQLite paging and filters.
    if (!query.has_filters() && query.pagination()?.is_none()) || state.sqlite_path.is_none() {
        if query.has_filters() {
            return Err(ApiError::ServiceUnavailable(
                "identity directory filtering requires SQLite storage".into(),
            ));
        }
        return legacy_identity_payload(
            state,
            &ClientListQuery {
                page: query.page,
                per_page: query.per_page,
            },
        );
    }
    let path = state.sqlite_path.as_ref().ok_or_else(|| {
        ApiError::ServiceUnavailable("identity directory requires SQLite storage".into())
    })?;
    // Only the actual runtime roster contributes transient names/voice ownership.
    // Do not clone its payloads or hydrate historical clients/announces.
    let overlays = state
        .clients
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .values()
        .filter(|record| client_should_appear_in_client_list(record))
        .filter_map(|record| {
            Some(IdentityDirectoryClientOverlay {
                identity: normalize_identity_key(&record.identity)?,
                display_name: record.display_name.clone(),
                voice_destination: record
                    .metadata
                    .get("voice")
                    .and_then(|voice| voice.get("destination_hash"))
                    .and_then(Value::as_str)
                    .and_then(normalize_identity_key),
            })
        })
        .collect::<Vec<_>>();
    let page = RchSqliteStore::open_read_only(path.as_ref())
        .and_then(|store| store.load_identity_directory_page(&resolved, &overlays))
        .map_err(|error| ApiError::Internal(format!("identity directory: {error}")))?;
    let announces = page
        .entries
        .iter()
        .filter_map(|entry| entry.announce.clone())
        .collect::<Vec<_>>();
    let modes = page
        .entries
        .iter()
        .filter_map(|entry| entry.rem_mode.clone())
        .collect::<Vec<_>>();
    let annotations = rem_annotations_from_records(&announces, &modes);
    let selected = page
        .entries
        .iter()
        .filter_map(|entry| normalize_identity_key(&entry.state.identity))
        .collect::<HashSet<_>>();
    let clients = state
        .clients
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .values()
        .filter_map(|record| {
            let key = normalize_identity_key(&record.identity)?;
            if !selected.contains(&key) {
                return None;
            }
            let mut record = record.clone();
            if let Some(annotation) = annotations.get(&key) {
                record.apply_rem_annotation(annotation);
            }
            client_should_appear_in_client_list(&record).then_some((key, record))
        })
        .collect::<HashMap<_, _>>();
    let items = page
        .entries
        .into_iter()
        .map(|entry| {
            let record = IdentityStatusRecord::from(entry.state);
            let key = record.identity_key();
            let mut value = record.to_python_value(annotations.get(&key));
            if let Some(client) = clients.get(&key) {
                merge_identity_payload_client_display_metadata(&mut value, client);
            }
            // Additive opt-in discovery time; preferred announce metadata stays intact.
            if query.has_filters() {
                value["RecentlyHeardAt"] = json!(entry.last_heard_ts_ms.map(iso8601_from_unix_ms));
            }
            value
        })
        .collect::<Vec<_>>();
    if let Some((number, size)) = query.pagination()? {
        let total_pages = page.total.div_ceil(size);
        return Ok(Json(
            json!({ "items": items, "page": number, "per_page": size,
            "total": page.total, "total_pages": total_pages, "has_next": number < total_pages, "has_previous": number > 1 }),
        ));
    }
    Ok(Json(json!(items)))
}

pub(super) fn openapi_operation() -> Value {
    let mut operation = openapi_paginated_list_operation(
        "IdentityStatus",
        "PaginatedIdentityList",
        "Identity moderation and discovery directory. Legacy calls return arrays; explicit paging bounds responses. Recent includes joined, team-linked, REM and moderated identities; recently heard is not online presence.",
    );
    let mut parameters = operation["parameters"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    for (name, description, values) in [
        (
            "view",
            "Optional recency filter. Defaults to all for legacy compatibility; UI requests recent.",
            vec!["recent", "all"],
        ),
        (
            "client_type",
            "Optional preferred announce client type filter.",
            vec!["all", "rem", "generic_lxmf"],
        ),
        (
            "order",
            "Stable ordering. Defaults to identity_asc; last_seen_desc uses newest discovery then canonical identity.",
            vec!["last_seen_desc", "identity_asc"],
        ),
        (
            "search",
            "Case-insensitive substring in identity, display name or advertised destination, within the selected view.",
            vec![],
        ),
        (
            "identity",
            "Exact canonical identity or advertised destination lookup; use view=all for historical enrichment.",
            vec![],
        ),
    ] {
        let mut parameter = json!({"name":name,"in":"query","required":false,"description":description,"schema":{"type":"string"}});
        if !values.is_empty() {
            parameter["schema"]["enum"] = json!(values);
        }
        parameters.push(parameter);
    }
    operation["parameters"] = json!(parameters);
    operation
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        ClientRecord, CoreIdentityStateRecord, Query, State, Uuid, app_info_payload,
        list_identities,
    };

    #[tokio::test]
    async fn sqlite_pages_apply_policy_and_lookup_before_materializing_payloads() {
        let directory = std::env::temp_dir().join(format!("rch-directory-http-{}", Uuid::new_v4()));
        std::fs::create_dir(&directory).expect("fixture");
        let path = directory.join("state.db");
        let now = unix_now_ms();
        let mut store = RchSqliteStore::open(&path).expect("store");
        let names = [
            "recent",
            "older",
            "banned",
            "blackholed",
            "rem",
            "joined",
            "voice",
            "alias-owner",
        ];
        store
            .upsert_identity_states(
                &names
                    .iter()
                    .map(|name| CoreIdentityStateRecord {
                        identity: (*name).to_string(),
                        is_banned: *name == "banned",
                        is_blackholed: *name == "blackholed",
                        updated_ts_ms: now,
                    })
                    .collect::<Vec<_>>(),
            )
            .expect("states");
        store
            .upsert_identity_announces(&[
                r3akt_rch_core::IdentityAnnounceRecord {
                    destination_hash: "dst-old".into(),
                    announced_identity_hash: Some("older".into()),
                    display_name: Some("Historical display".into()),
                    source_interface: Some("destination".into()),
                    announce_capabilities: vec![],
                    client_type: "generic_lxmf".into(),
                    first_seen_ts_ms: 0,
                    last_seen_ts_ms: 0,
                },
                r3akt_rch_core::IdentityAnnounceRecord {
                    destination_hash: "dst-recent".into(),
                    announced_identity_hash: Some("recent".into()),
                    display_name: Some("Fresh display".into()),
                    source_interface: Some("destination".into()),
                    announce_capabilities: vec![],
                    client_type: "generic_lxmf".into(),
                    first_seen_ts_ms: now,
                    last_seen_ts_ms: now,
                },
                r3akt_rch_core::IdentityAnnounceRecord {
                    destination_hash: "dst-rem".into(),
                    announced_identity_hash: Some("rem".into()),
                    display_name: None,
                    source_interface: None,
                    announce_capabilities: vec![],
                    client_type: "rem".into(),
                    first_seen_ts_ms: 0,
                    last_seen_ts_ms: 0,
                },
            ])
            .expect("announces");
        drop(store);
        let state = AppState::from_sqlite_path(&path).expect("state");
        let mut voice_owner = ClientRecord::new("alias-owner".into(), now);
        voice_owner.metadata = json!({"voice":{"destination_hash":"voice"}});
        state
            .clients
            .write()
            .expect("clients")
            .insert("alias-owner".into(), voice_owner);
        state
            .clients
            .write()
            .expect("clients")
            .insert("joined".into(), ClientRecord::new("joined".into(), now));
        let parse = |value| serde_json::from_value::<IdentityListQuery>(value).expect("query");
        let Json(recent) = list_identities(
            State(state.clone()),
            Query(parse(
                json!({"page":1,"per_page":50,"view":"recent","order":"last_seen_desc"}),
            )),
        )
        .await
        .expect("recent");
        assert_eq!(recent["total"], 6);
        assert_eq!(recent["items"][0]["Identity"], "recent");
        assert_eq!(
            recent["items"][0]["RecentlyHeardAt"],
            iso8601_from_unix_ms(now)
        );
        let Json(history) = list_identities(
            State(state.clone()),
            Query(parse(
                json!({"page":1,"per_page":1,"view":"all","search":"HISTORICAL"}),
            )),
        )
        .await
        .expect("history");
        assert_eq!(history["total"], 1);
        assert_eq!(history["items"][0]["Identity"], "older");
        let Json(exact) = list_identities(
            State(state.clone()),
            Query(parse(
                json!({"page":1,"per_page":1,"view":"all","identity":" DST-OLD "}),
            )),
        )
        .await
        .expect("exact destination");
        assert_eq!(exact["items"], history["items"]);
        let Json(array) = list_identities(
            State(state.clone()),
            Query(parse(json!({"view":"all","identity":"older"}))),
        )
        .await
        .expect("filtered array");
        assert!(array.is_array());
        let Json(empty) = list_identities(
            State(state.clone()),
            Query(parse(json!({"page":99,"per_page":50,"view":"all"}))),
        )
        .await
        .expect("empty page");
        assert_eq!(empty["items"], json!([]));
        assert!(
            app_info_payload(&state)["identity_directory"]["supported"]
                .as_bool()
                .expect("supported")
        );
        for query in [
            json!({"page":0}),
            json!({"per_page":501}),
            json!({"view":"today"}),
            json!({"order":"other"}),
            json!({"client_type":"other"}),
            json!({"identity":" "}),
        ] {
            assert!(matches!(
                list_identities(State(state.clone()), Query(parse(query))).await,
                Err(ApiError::Unprocessable(_))
            ));
        }
        std::fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn in_memory_runtime_reports_unsupported_filtering_and_configurable_defaults() {
        let state = AppState::default()
            .with_identity_directory_config(IdentityDirectoryConfig {
                page_size: 25,
                recent_hours: 48,
                lookup_max_entries: 100,
                lookup_concurrency: 2,
            })
            .expect("policy");
        let info = app_info_payload(&state);
        assert_eq!(
            info["identity_directory"],
            json!({"supported":false,"page_size":25,"recent_hours":48,"lookup_max_entries":100,"lookup_concurrency":2})
        );
        assert!(matches!(
            list(
                &state,
                &IdentityListQuery {
                    view: Some("recent".into()),
                    ..Default::default()
                }
            ),
            Err(ApiError::ServiceUnavailable(_))
        ));
    }
}
