use super::*;
pub(super) fn outgoing(
    unit: &RchCommandTransaction<'_>,
    _event: &InboxEvent,
    index: usize,
    destination: &str,
    content: &str,
    fields: Value,
    created: i64,
) -> Result<OutboundMessageRecord, ApiError> {
    if index >= 256 {
        return Err(ApiError::ServiceUnavailable(
            "durable fanout recipient bound reached; input retained".into(),
        ));
    }
    let operation = sha256_lower_hex(
        format!(
            "{}:{index}:{destination}",
            unit.inbox_event_key().map_err(storage)?
        )
        .as_bytes(),
    );
    let record = OutboundMessageRecord {
        message_id: operation.clone(),
        topic_id: None,
        destination: Some(destination.into()),
        sender: "r3akt-rch-server".into(),
        content: content.into(),
        delivery_mode: DeliveryMode::Targeted,
        delivery_method: "durable_broker".into(),
        delivery_policy_reason: "inbox_application".into(),
        delivery_state: "broker_pending".into(),
        delivery_metadata: json!({"direction":"outbound","lxmf_fields":fields}),
        created_ts_ms: created,
        attachments: Vec::new(),
    };
    unit.stage_outbound_intent(&DurableOutboundIntent {operation_id:operation.clone(),message:CoreMessageRecord::from(record.clone()),request:json!({"identity":"","operation_id":operation,"destination":destination,"title":"RCH","content":content,"fields":fields,"options":{"method":"direct","try_propagation_on_fail":true}})}).map_err(storage)?;
    Ok(record)
}

fn command_alias(command: &r3akt_protocol::Command) -> r3akt_protocol::Command {
    let mut result = command.clone();
    let name = command.name.trim().to_ascii_lowercase();
    result.name = match name.as_str() {
        name if is_join_command_name(name) => "mission.join",
        "leave" => "mission.leave",
        "pause" => "mission.pause",
        "resume" => "mission.resume",
        "nick" | "nickname" => "mission.nick",
        "users" => "mission.users",
        "createtopic" | "create_topic" => "topic.create",
        "subscribetopic" | "subscribe_topic" => "topic.subscribe",
        "publishmessage" => "mission.message.send",
        _ => name.as_str(),
    }
    .into();
    if result.name == "mission.nick" {
        if let Some(nickname) =
            command_arg_text_with_position(&command.args, &["nickname", "nick", "name"], 0)
        {
            result.args["nickname"] = json!(nickname);
        }
    }
    if result.name == "topic.subscribe" {
        if let Some(topic) = command_topic_id(command) {
            result.args["topic_id"] = json!(topic);
        }
    }
    result
}

pub(super) fn apply_envelope(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    bootstrap: bool,
    published: &mut Vec<OutboundMessageRecord>,
    telemetry: &mut Vec<TelemetryRecord>,
    allowlist: Option<&HashSet<String>>,
) -> Result<(), ApiError> {
    let source = normalize_identity_key(envelope.source.as_str());
    if !bootstrap
        && unit.core_mut().identity_states().iter().any(|s| {
            normalize_identity_key(&s.identity) == source && (s.is_banned || s.is_blackholed)
        })
    {
        unit.reject("inbound identity is banned or blackholed")
            .map_err(storage)?;
        return Ok(());
    }
    fn allowed(core: &mut RchCore, destination: &str, allowlist: Option<&HashSet<String>>) -> bool {
        let key = normalize_identity_key(destination);
        !core
            .identity_states()
            .iter()
            .any(|s| normalize_identity_key(&s.identity) == key && (s.is_banned || s.is_blackholed))
            && allowlist.is_none_or(|set| key.as_ref().is_some_and(|k| set.contains(k)))
    }
    let command = match &envelope.payload {
        Payload::Command(command) => Some(command.clone()),
        Payload::TopicMessage(message) => plain_lxmf_command_from_message_body(&message.body),
        _ => None,
    };
    if let Some(command) = command {
        if bootstrap {
            return Ok(());
        }
        if command.name == "telemetry.collect" {
            return super::telemetry_collector::reply(
                unit, event, envelope, &command, published, allowlist,
            );
        }
        if command.name.eq_ignore_ascii_case("help") {
            published.push(outgoing(
                unit,
                event,
                published.len(),
                envelope.source.as_str(),
                &plain_lxmf_help_reply(),
                json!({}),
                envelope.timestamp.timestamp_millis(),
            )?);
            return Ok(());
        }
        let command = command_alias(&command);
        let mission = mission_sync_command_from_reticulumd(envelope, &command);
        let logical = format!("command:{}", mission.command_id);
        if !unit
            .claim_logical_input(
                envelope.source.as_str(),
                &logical,
                &json!({"name":command.name,"args":command.args}),
            )
            .map_err(storage)?
        {
            return Ok(());
        }
        let checklist = is_supported_checklist_command(&command.name);
        let mut responses = if checklist {
            unit.core_mut().handle_checklist_sync_command(&mission)
        } else {
            unit.core_mut().handle_mission_sync_command(&mission)
        };
        if !responses
            .iter()
            .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected"))
        {
            let generated = unit.core_mut().messages().to_vec();
            if generated.len() > 1 {
                return Err(ApiError::Internal(
                    "command generated more than one business message".into(),
                ));
            }
            for message in generated {
                let mut message = OutboundMessageRecord::from(message);
                message.message_id = sha256_lower_hex(
                    serde_json::to_vec(&("inbound-command", &source, &logical))
                        .map_err(|e| ApiError::Internal(e.to_string()))?
                        .as_slice(),
                );
                let snapshot = unit.core_mut().snapshot();
                let now = event.created_at.saturating_mul(1000);
                let candidates = match message.delivery_mode {
                    DeliveryMode::Targeted => {
                        message.destination.iter().cloned().collect::<Vec<_>>()
                    }
                    DeliveryMode::Fanout => snapshot
                        .subscribers
                        .iter()
                        .filter(|r| Some(&r.topic_id) == message.topic_id.as_ref())
                        .map(|r| r.node_id.clone())
                        .filter(|d| normalize_identity_key(d) != source)
                        .collect(),
                    DeliveryMode::Broadcast => snapshot
                        .clients
                        .iter()
                        .filter(|c| {
                            !c.paused
                                && now.saturating_sub(c.last_seen_ts_ms)
                                    <= REM_PEER_ACTIVE_WINDOW_MS
                        })
                        .map(|c| c.identity.clone())
                        .filter(|d| normalize_identity_key(d) != source)
                        .collect(),
                };
                let mut destinations = candidates
                    .into_iter()
                    .filter_map(|d| reticulum_destination_hash(&d))
                    .filter(|d| allowed(unit.core_mut(), d, allowlist))
                    .map(|d| {
                        let text_only = snapshot
                            .clients
                            .iter()
                            .any(|c| c.identity.eq_ignore_ascii_case(&d) && c.text_only);
                        (d, text_only)
                    })
                    .collect::<Vec<_>>();
                destinations.sort();
                destinations.dedup();
                match super::outbound::stage_business_message(unit, message, destinations) {
                    Ok(message) => published.push(message),
                    Err(ApiError::BadRequest(reason)) => {
                        unit.reject(&reason).map_err(storage)?;
                        responses = vec![r3akt_rch_core::MissionSyncResponse::results(
                            r3akt_profile_rch::CommandResultEnvelope {
                                command_id: mission.command_id.clone(),
                                status: r3akt_profile_rch::CommandResultStatus::Rejected,
                                detail: None,
                                reason_code: Some("invalid_payload".into()),
                                reason: Some(reason),
                                required_capabilities: vec![],
                                accepted_at: None,
                                by_identity: None,
                                correlation_id: mission.correlation_id.clone(),
                                result: Value::Null,
                            },
                        )];
                    }
                    Err(error) => return Err(error),
                }
            }
        }
        let rejected = responses.iter().any(|r| {
            r.results_field()
                .and_then(|v| v.get("status"))
                .and_then(Value::as_str)
                == Some("rejected")
        });
        if rejected {
            unit.reject("domain command rejected; see persisted response intent")
                .map_err(storage)?;
        }
        let team = command.args.get("_rem_team_uid").and_then(Value::as_str);
        let mut destinations = team
            .map(|team| {
                unit.core_mut()
                    .rem_team_routing_destinations(envelope.source.as_str(), team)
            })
            .unwrap_or_default();
        destinations.retain(|d| allowed(unit.core_mut(), d, allowlist));
        for response in responses {
            let fields = rem_team_routing::mission_response_fields(&response, team)?;
            if allowed(unit.core_mut(), envelope.source.as_str(), allowlist) {
                published.push(outgoing(
                    unit,
                    event,
                    published.len(),
                    envelope.source.as_str(),
                    &response.content,
                    fields.clone(),
                    envelope.timestamp.timestamp_millis(),
                )?);
            }
            if response.event_field().is_some() && !rejected {
                if team.is_none() {
                    if let Some(mission) = mission_uid_from_response_fields(&response) {
                        let snapshot = unit.core_mut().snapshot();
                        let teams = snapshot
                            .mission_team_links
                            .iter()
                            .filter(|link| link.mission_uid == mission)
                            .map(|link| link.team_uid.clone())
                            .collect::<Vec<_>>();
                        let members = snapshot
                            .team_members
                            .iter()
                            .filter(|member| {
                                member
                                    .team_uid
                                    .as_ref()
                                    .is_some_and(|team| teams.contains(team))
                            })
                            .map(|member| member.uid.clone())
                            .collect::<HashSet<_>>();
                        destinations = snapshot
                            .team_members
                            .iter()
                            .filter(|member| members.contains(&member.uid))
                            .map(|member| member.rns_identity.as_str())
                            .chain(
                                snapshot
                                    .team_member_client_links
                                    .iter()
                                    .filter(|link| members.contains(&link.team_member_uid))
                                    .map(|link| link.client_identity.as_str()),
                            )
                            .filter_map(reticulum_destination_hash)
                            .filter(|d| normalize_identity_key(d) != source)
                            .collect();
                        destinations.sort();
                        destinations.dedup();
                        destinations.retain(|d| allowed(unit.core_mut(), d, allowlist));
                    }
                }
                for destination in &destinations {
                    published.push(outgoing(
                        unit,
                        event,
                        published.len(),
                        destination,
                        &response.content,
                        fields.clone(),
                        envelope.timestamp.timestamp_millis(),
                    )?);
                }
            }
        }
        return Ok(());
    }
    match &envelope.payload {
        Payload::TopicMessage(message) => {
            let body = match sanitize_group_chat_text(&message.body) {
                Ok(value) => value,
                Err(reason) => {
                    unit.reject(&reason).map_err(storage)?;
                    return Ok(());
                }
            };
            // Validate all input before staging any SQL effects in this unit of work.
            if message.attachments.iter().any(|attachment| {
                attachment.data.len() > r3akt_rch_core::MAX_DURABLE_ATTACHMENT_BYTES
            }) {
                unit.reject("attachment exceeds durable byte limit")
                    .map_err(storage)?;
                return Ok(());
            }
            let mut attachments = Vec::new();
            for attachment in &message.attachments {
                let category = normalized_inbound_attachment_category(&attachment.category);
                let name = sanitize_attachment_filename(&attachment.name);
                let record = unit
                    .stage_attachment(
                        FileAttachmentRecord {
                            file_id: 0,
                            name,
                            path: String::new(),
                            category: category.into(),
                            size: attachment.data.len() as u64,
                            media_type: attachment.media_type.clone(),
                            topic_id: Some(envelope.topic.to_string()),
                            created_ts_ms: envelope.timestamp.timestamp_millis(),
                            updated_ts_ms: envelope.timestamp.timestamp_millis(),
                        },
                        &attachment.data,
                    )
                    .map_err(storage)?;
                attachments.push(chat_attachment_from_file_record(&record));
            }
            let inbound = OutboundMessageRecord {
                message_id: envelope.id.to_string(),
                topic_id: Some(envelope.topic.to_string()),
                destination: match &envelope.destination {
                    Destination::Node(n) => Some(n.to_string()),
                    _ => None,
                },
                sender: envelope.source.to_string(),
                content: body.clone(),
                delivery_mode: DeliveryMode::Targeted,
                delivery_method: "reticulumd_inbound".into(),
                delivery_policy_reason: "durable_broker".into(),
                delivery_state: "received".into(),
                delivery_metadata: json!({"direction":"inbound","reticulumd_inbound":true}),
                created_ts_ms: envelope.timestamp.timestamp_millis(),
                attachments,
            };
            unit.stage_message(&CoreMessageRecord::from(inbound.clone()))
                .map_err(storage)?;
            published.push(inbound);
            let prior = unit
                .core_mut()
                .clients()
                .into_iter()
                .find(|c| c.identity.eq_ignore_ascii_case(envelope.source.as_str()));
            let mut client = prior.unwrap_or(r3akt_rch_core::ClientRecord {
                identity: envelope.source.to_string(),
                first_seen_ts_ms: event.created_at.saturating_mul(1000),
                last_seen_ts_ms: event.created_at.saturating_mul(1000),
                nickname: None,
                role: "member".into(),
                paused: false,
                text_only: false,
                last_chat_ts_ms: None,
            });
            if !bootstrap {
                let observed = event.created_at.saturating_mul(1000);
                client.last_seen_ts_ms = client.last_seen_ts_ms.max(observed);
                client.last_chat_ts_ms = Some(client.last_chat_ts_ms.unwrap_or(0).max(observed));
                unit.stage_client(&client).map_err(storage)?;
            }
            if !bootstrap {
                let mut destinations = unit
                    .core_mut()
                    .subscribers(envelope.topic.as_str())
                    .into_iter()
                    .map(|s| s.node_id)
                    .filter(|d| normalize_identity_key(d) != source)
                    .collect::<Vec<_>>();
                if destinations.is_empty() && envelope.topic.as_str() == "direct" {
                    destinations = unit
                        .core_mut()
                        .clients()
                        .into_iter()
                        .filter(|c| !c.paused && normalize_identity_key(&c.identity) != source)
                        .map(|c| c.identity)
                        .collect();
                }
                destinations.retain(|d| allowed(unit.core_mut(), d, allowlist));
                let now = event.created_at.saturating_mul(1000);
                let roster = unit.core_mut().clients();
                if envelope.topic.as_str() == "direct" {
                    destinations.retain(|d| {
                        roster.iter().any(|c| {
                            c.identity.eq_ignore_ascii_case(d)
                                && now.saturating_sub(c.last_seen_ts_ms)
                                    <= REM_PEER_ACTIVE_WINDOW_MS
                        })
                    });
                }
                destinations.sort();
                destinations.dedup();
                let sender = client
                    .nickname
                    .as_deref()
                    .unwrap_or(envelope.source.as_str());
                let fields = if message.attachments.is_empty() {
                    json!({})
                } else {
                    json!({LXMF_FIELD_ATTACHMENTS_PUBLIC_KEY.to_string():message.attachments.iter().map(|a|json!({"name":a.name,"data":format!("base64:{}",BASE64_STANDARD.encode(&a.data))})).collect::<Vec<_>>()})
                };
                if destinations.len() > 256
                    || fields
                        .to_string()
                        .len()
                        .saturating_add(body.len())
                        .saturating_mul(destinations.len())
                        > 32 * 1024 * 1024
                {
                    return Err(ApiError::ServiceUnavailable(
                        "fanout byte/count budget exceeded; input retained".into(),
                    ));
                }
                for destination in &destinations {
                    let fields = if roster
                        .iter()
                        .any(|c| c.identity.eq_ignore_ascii_case(destination) && c.text_only)
                    {
                        json!({})
                    } else {
                        fields.clone()
                    };
                    published.push(outgoing(
                        unit,
                        event,
                        published.len(),
                        destination,
                        &format!("{sender} > {body}"),
                        fields,
                        envelope.timestamp.timestamp_millis(),
                    )?);
                }
            }
        }
        Payload::TelemetrySample(t) => {
            let record = r3akt_rch_core::TelemetryRecord {
                packed_telemeter: t.packed_telemeter.clone(),
                peer_destination: envelope.source.to_string(),
                timestamp_s: t.timestamp_s.unwrap_or(envelope.timestamp.timestamp()),
                telemetry: t.telemetry.clone(),
                display_name: None,
                identity_label: None,
            };
            telemetry.push(unit.stage_telemetry(&record).map_err(storage)?);
        }
        Payload::HealthTelemetry(t) => {
            let record = r3akt_rch_core::TelemetryRecord {
                packed_telemeter: None,
                peer_destination: envelope.source.to_string(),
                timestamp_s: t.observed_at.timestamp(),
                telemetry: health_telemetry_payload(t),
                display_name: None,
                identity_label: None,
            };
            telemetry.push(unit.stage_telemetry(&record).map_err(storage)?);
        }
        _ => {}
    }
    Ok(())
}

#[cfg(test)]
mod tests;
