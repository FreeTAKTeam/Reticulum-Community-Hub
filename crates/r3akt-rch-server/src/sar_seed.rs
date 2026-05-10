use std::collections::BTreeMap;
use std::fmt::{self, Write as _};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

pub const SCENARIO_ID: &str = "sar-spruce-ridge-2026";
pub const MISSION_UID: &str = SCENARIO_ID;

#[derive(Debug, Clone)]
pub struct SarSeedOptions {
    pub base_url: String,
    pub api_key: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SarSeedSummary {
    pub scenario_id: String,
    pub mission_uid: String,
    pub upserted: BTreeMap<String, usize>,
    pub created: BTreeMap<String, usize>,
    pub found: BTreeMap<String, usize>,
    pub object_ids: BTreeMap<String, Vec<String>>,
}

impl SarSeedSummary {
    fn new() -> Self {
        Self {
            scenario_id: SCENARIO_ID.to_string(),
            mission_uid: MISSION_UID.to_string(),
            upserted: BTreeMap::new(),
            created: BTreeMap::new(),
            found: BTreeMap::new(),
            object_ids: BTreeMap::new(),
        }
    }

    fn bump_upserted(&mut self, kind: &str) {
        *self.upserted.entry(kind.to_string()).or_insert(0) += 1;
    }

    fn bump_created(&mut self, kind: &str) {
        *self.created.entry(kind.to_string()).or_insert(0) += 1;
    }

    fn bump_found(&mut self, kind: &str) {
        *self.found.entry(kind.to_string()).or_insert(0) += 1;
    }

    fn push_id(&mut self, kind: &str, id: impl Into<String>) {
        self.object_ids
            .entry(kind.to_string())
            .or_default()
            .push(id.into());
    }
}

#[derive(Debug)]
pub enum SarSeedError {
    InvalidBaseUrl(String),
    Io(std::io::Error),
    Json(serde_json::Error),
    HttpStatus {
        method: String,
        path: String,
        status: u16,
        body: String,
    },
    HttpProtocol(String),
    MissingField(String),
}

impl fmt::Display for SarSeedError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidBaseUrl(url) => write!(f, "unsupported base URL: {url}"),
            Self::Io(error) => write!(f, "{error}"),
            Self::Json(error) => write!(f, "{error}"),
            Self::HttpStatus {
                method,
                path,
                status,
                body,
            } => write!(f, "{method} {path} returned HTTP {status}: {body}"),
            Self::HttpProtocol(message) => write!(f, "HTTP protocol error: {message}"),
            Self::MissingField(field) => write!(f, "missing response field: {field}"),
        }
    }
}

impl std::error::Error for SarSeedError {}

impl From<std::io::Error> for SarSeedError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for SarSeedError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

#[derive(Debug, Clone)]
struct HttpEndpoint {
    host: String,
    port: u16,
    base_path: String,
}

impl HttpEndpoint {
    fn parse(base_url: &str) -> Result<Self, SarSeedError> {
        let Some(rest) = base_url.strip_prefix("http://") else {
            return Err(SarSeedError::InvalidBaseUrl(base_url.to_string()));
        };
        let (host_port, path) = rest.split_once('/').unwrap_or((rest, ""));
        let (host, port) = match host_port.rsplit_once(':') {
            Some((host, port)) => {
                let port = port
                    .parse::<u16>()
                    .map_err(|_| SarSeedError::InvalidBaseUrl(base_url.to_string()))?;
                (host.to_string(), port)
            }
            None => (host_port.to_string(), 80),
        };
        if host.is_empty() {
            return Err(SarSeedError::InvalidBaseUrl(base_url.to_string()));
        }
        let base_path = if path.is_empty() {
            String::new()
        } else {
            format!("/{}", path.trim_end_matches('/'))
        };
        Ok(Self {
            host,
            port,
            base_path,
        })
    }

    fn path(&self, path: &str) -> String {
        format!("{}{}", self.base_path, path)
    }
}

#[derive(Debug)]
struct SarHttpClient {
    endpoint: HttpEndpoint,
    api_key: Option<String>,
}

impl SarHttpClient {
    fn new(options: &SarSeedOptions) -> Result<Self, SarSeedError> {
        Ok(Self {
            endpoint: HttpEndpoint::parse(&options.base_url)?,
            api_key: options.api_key.clone(),
        })
    }

    fn get_json(&self, path: &str) -> Result<Value, SarSeedError> {
        self.request_json("GET", path, None)
    }

    fn post_json(&self, path: &str, body: Value) -> Result<Value, SarSeedError> {
        self.request_json("POST", path, Some(body))
    }

    fn put_json(&self, path: &str, body: Value) -> Result<Value, SarSeedError> {
        self.request_json("PUT", path, Some(body))
    }

    fn request_json(
        &self,
        method: &str,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, SarSeedError> {
        let bytes = body
            .map(|value| serde_json::to_vec(&value))
            .transpose()?
            .unwrap_or_default();
        let content_type = (!bytes.is_empty()).then_some("application/json");
        let response = self.request(method, path, content_type, &bytes)?;
        if response.body.trim().is_empty() {
            Ok(json!({}))
        } else {
            Ok(serde_json::from_str(&response.body)?)
        }
    }

    fn upload_attachment(
        &self,
        filename: &str,
        media_type: &str,
        topic_id: &str,
        bytes: &[u8],
    ) -> Result<Value, SarSeedError> {
        let boundary = format!("{SCENARIO_ID}-boundary");
        let sha256 = Sha256::digest(bytes)
            .iter()
            .fold(String::new(), |mut output, byte| {
                write!(&mut output, "{byte:02x}").expect("write sha256 hex");
                output
            });
        let body =
            multipart_attachment_body(&boundary, filename, media_type, bytes, &sha256, topic_id);
        let response = self.request(
            "POST",
            "/Chat/Attachment",
            Some(&format!("multipart/form-data; boundary={boundary}")),
            &body,
        )?;
        Ok(serde_json::from_str(&response.body)?)
    }

    fn request(
        &self,
        method: &str,
        path: &str,
        content_type: Option<&str>,
        body: &[u8],
    ) -> Result<HttpResponse, SarSeedError> {
        let full_path = self.endpoint.path(path);
        let mut stream = TcpStream::connect((self.endpoint.host.as_str(), self.endpoint.port))?;
        stream.set_read_timeout(Some(Duration::from_secs(20)))?;
        stream.set_write_timeout(Some(Duration::from_secs(20)))?;
        let mut request = format!(
            "{method} {full_path} HTTP/1.1\r\nHost: {}\r\nAccept: application/json\r\nConnection: close\r\nContent-Length: {}\r\n",
            self.endpoint.host,
            body.len()
        );
        if let Some(api_key) = &self.api_key {
            write!(&mut request, "X-API-Key: {api_key}\r\n").expect("write request header");
        }
        if let Some(content_type) = content_type {
            write!(&mut request, "Content-Type: {content_type}\r\n").expect("write request header");
        }
        request.push_str("\r\n");
        stream.write_all(request.as_bytes())?;
        stream.write_all(body)?;
        stream.flush()?;

        let mut response = Vec::new();
        let mut chunk = [0_u8; 4096];
        loop {
            let read = stream.read(&mut chunk)?;
            if read == 0 {
                break;
            }
            response.extend_from_slice(&chunk[..read]);
            if complete_http_response(&response).is_some_and(|complete| complete) {
                break;
            }
        }
        let response = parse_http_response(method, path, &response)?;
        if !(200..300).contains(&response.status) {
            return Err(SarSeedError::HttpStatus {
                method: method.to_string(),
                path: path.to_string(),
                status: response.status,
                body: response.body,
            });
        }
        Ok(response)
    }
}

fn complete_http_response(bytes: &[u8]) -> Option<bool> {
    let header_end = bytes.windows(4).position(|window| window == b"\r\n\r\n")?;
    let headers = String::from_utf8_lossy(&bytes[..header_end]);
    let body = &bytes[header_end + 4..];
    if is_chunked(&headers) {
        return Some(chunked_body_complete(body));
    }
    let Some(content_length) = headers.lines().find_map(|line| {
        let (name, value) = line.split_once(':')?;
        name.eq_ignore_ascii_case("content-length")
            .then(|| value.trim().parse::<usize>().ok())
            .flatten()
    }) else {
        return Some(true);
    };
    Some(bytes.len() >= header_end + 4 + content_length)
}

#[derive(Debug)]
struct HttpResponse {
    status: u16,
    body: String,
}

fn parse_http_response(
    method: &str,
    path: &str,
    bytes: &[u8],
) -> Result<HttpResponse, SarSeedError> {
    let header_end = bytes
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| SarSeedError::HttpProtocol(format!("{method} {path} missing header end")))?;
    let headers = String::from_utf8_lossy(&bytes[..header_end]);
    let status = headers
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|status| status.parse::<u16>().ok())
        .ok_or_else(|| SarSeedError::HttpProtocol(format!("{method} {path} missing status")))?;
    let body_bytes = &bytes[header_end + 4..];
    let body_bytes = if is_chunked(&headers) {
        decode_chunked_body(body_bytes)?
    } else {
        body_bytes.to_vec()
    };
    let body = String::from_utf8_lossy(&body_bytes).to_string();
    Ok(HttpResponse { status, body })
}

fn is_chunked(headers: &str) -> bool {
    headers.lines().any(|line| {
        let Some((name, value)) = line.split_once(':') else {
            return false;
        };
        name.eq_ignore_ascii_case("transfer-encoding")
            && value
                .split(',')
                .any(|part| part.trim().eq_ignore_ascii_case("chunked"))
    })
}

fn chunked_body_complete(bytes: &[u8]) -> bool {
    decode_chunked_body(bytes).is_ok()
}

fn decode_chunked_body(bytes: &[u8]) -> Result<Vec<u8>, SarSeedError> {
    let mut decoded = Vec::new();
    let mut offset = 0;
    loop {
        let Some(line_end) = bytes[offset..]
            .windows(2)
            .position(|window| window == b"\r\n")
            .map(|position| offset + position)
        else {
            return Err(SarSeedError::HttpProtocol(
                "incomplete chunk size".to_string(),
            ));
        };
        let size_text = String::from_utf8_lossy(&bytes[offset..line_end]);
        let size_text = size_text.split(';').next().unwrap_or("").trim();
        let size = usize::from_str_radix(size_text, 16)
            .map_err(|_| SarSeedError::HttpProtocol("invalid chunk size".to_string()))?;
        offset = line_end + 2;
        if size == 0 {
            return if bytes.len() >= offset + 2 {
                Ok(decoded)
            } else {
                Err(SarSeedError::HttpProtocol(
                    "incomplete chunk trailer".to_string(),
                ))
            };
        }
        if bytes.len() < offset + size + 2 {
            return Err(SarSeedError::HttpProtocol("incomplete chunk".to_string()));
        }
        decoded.extend_from_slice(&bytes[offset..offset + size]);
        offset += size;
        if bytes.get(offset..offset + 2) != Some(b"\r\n") {
            return Err(SarSeedError::HttpProtocol(
                "missing chunk terminator".to_string(),
            ));
        }
        offset += 2;
    }
}

pub fn narrative_timeline() -> Vec<&'static str> {
    vec![
        "18:40 LKP confirmed at Spruce Ridge north trail register; solo hiker overdue by 6 hours.",
        "19:05 ICP established at Spruce Ridge fire road gate; weather trending cold rain and fog.",
        "19:25 Alpha Ground assigned drainage sweep from LKP to creek junction.",
        "19:40 Bravo Ground assigned ridge contour search toward the old lookout spur.",
        "20:05 Clue 1 found: torn blue rain-shell fabric on alder branch near the creek crossing.",
        "20:22 Medical staged for hypothermia extraction; LZ marked at quarry shelf.",
        "20:45 Comms sets relay on ridge knoll after handheld radio dropouts in the drainage.",
        "21:10 Boot print and trekking-pole mark shift probability into high-risk drainage.",
        "21:35 Subject located conscious but hypothermic below the drainage lip; litter requested.",
        "22:05 Extraction route fixed through Bravo grid; demobilization checklist opened.",
    ]
}

pub fn print_narrative_timeline() {
    println!("SAR narrative: Spruce Ridge Missing Hiker");
    for entry in narrative_timeline() {
        println!("- {entry}");
    }
}

pub fn seed_sar_scenario(options: &SarSeedOptions) -> Result<SarSeedSummary, SarSeedError> {
    let client = SarHttpClient::new(options)?;
    let mut summary = SarSeedSummary::new();
    check_server(&client)?;
    seed_topics(&client, &mut summary)?;
    seed_mission(&client, &mut summary)?;
    seed_teams_members_and_access(&client, &mut summary)?;
    seed_markers_and_zones(&client, &mut summary)?;
    seed_checklists(&client, &mut summary)?;
    seed_assets_skills_assignments(&client, &mut summary)?;
    seed_eam(&client, &mut summary)?;
    seed_attachments(&client, &mut summary)?;
    seed_timeline(&client, &mut summary)?;
    verify_major_objects(&client)?;
    Ok(summary)
}

fn check_server(client: &SarHttpClient) -> Result<(), SarSeedError> {
    client
        .get_json("/api/v1/auth/validate")
        .or_else(|_| client.get_json("/Status"))?;
    Ok(())
}

fn seed_topics(client: &SarHttpClient, summary: &mut SarSeedSummary) -> Result<(), SarSeedError> {
    for (id, name, description) in topics() {
        client.post_json(
            "/Topic",
            json!({
                "TopicID": id,
                "TopicName": name,
                "TopicPath": id.replace('.', "/"),
                "TopicDescription": description
            }),
        )?;
        summary.bump_upserted("topics");
        summary.push_id("topics", id);
    }
    let topic_ids = topics()
        .into_iter()
        .map(|(topic_id, _, _)| topic_id)
        .collect::<Vec<_>>();
    for (index, identity) in identities().into_iter().enumerate() {
        let topic_id = &topic_ids[index % topic_ids.len()];
        let subscriber_id = format!("{SCENARIO_ID}-sub-{identity}-{topic_id}");
        client.post_json(
            "/Subscriber/Add",
            json!({
                "SubscriberID": subscriber_id,
                "TopicID": topic_id,
                "Destination": identity,
                "Metadata": {
                    "scenario_id": SCENARIO_ID,
                    "identity": identity,
                    "role": simulated_role(identity)
                }
            }),
        )?;
        summary.bump_upserted("subscribers");
    }
    Ok(())
}

fn seed_mission(client: &SarHttpClient, summary: &mut SarSeedSummary) -> Result<(), SarSeedError> {
    client.post_json(
        "/api/r3akt/missions",
        json!({
            "uid": MISSION_UID,
            "mission_name": "SAR - Spruce Ridge Missing Hiker",
            "description": "Missing solo hiker last seen on Spruce Ridge north trail. Night operational period with deteriorating rain, fog, radio shadows in drainage, and hypothermia risk.",
            "topic_id": topic_id("command"),
            "default_role": "MISSION_SUBSCRIBER",
            "metadata": {
                "scenario_id": SCENARIO_ID,
                "incident_type": "Search and Rescue",
                "last_known_point": "Spruce Ridge north trail register",
                "operational_period": "2026-02-17T18:30:00Z/2026-02-18T02:00:00Z"
            }
        }),
    )?;
    summary.bump_upserted("missions");
    summary.push_id("missions", MISSION_UID);
    client.put_json(
        &format!("/api/r3akt/missions/{MISSION_UID}/rde"),
        json!({ "role": "MISSION_OWNER" }),
    )?;
    summary.bump_upserted("mission_rde");
    Ok(())
}

fn seed_teams_members_and_access(
    client: &SarHttpClient,
    summary: &mut SarSeedSummary,
) -> Result<(), SarSeedError> {
    for team in teams() {
        client.post_json(
            "/api/r3akt/teams",
            json!({
                "uid": team.uid,
                "mission_uid": MISSION_UID,
                "team_name": team.name,
                "color": team.color,
                "team_description": team.description
            }),
        )?;
        client.put_json(
            &format!("/api/r3akt/teams/{}/missions/{MISSION_UID}", team.uid),
            json!({}),
        )?;
        summary.bump_upserted("teams");
        summary.push_id("teams", team.uid);
    }
    for member in members() {
        client.post_json(
            "/api/r3akt/team-members",
            json!({
                "uid": member.uid,
                "team_uid": member.team_uid,
                "rns_identity": member.rns_identity,
                "display_name": member.display_name,
                "callsign": member.callsign,
                "role": member.role
            }),
        )?;
        client.put_json(
            &format!(
                "/api/r3akt/team-members/{}/clients/{}",
                member.uid, member.client_identity
            ),
            json!({}),
        )?;
        let role = if member.role == "HQ" {
            "MISSION_OWNER"
        } else {
            "MISSION_SUBSCRIBER"
        };
        client.put_json(
            "/api/r3akt/rights/mission-access",
            json!({
                "mission_uid": MISSION_UID,
                "subject_type": "team_member",
                "subject_id": member.uid,
                "role": role,
                "assigned_by": "sar-ic"
            }),
        )?;
        summary.bump_upserted("team_members");
        summary.push_id("team_members", member.uid);
    }
    Ok(())
}

fn seed_markers_and_zones(
    client: &SarHttpClient,
    summary: &mut SarSeedSummary,
) -> Result<(), SarSeedError> {
    let existing_markers = client.get_json("/api/markers")?;
    for marker in markers() {
        let marker_id = find_by_name(&existing_markers, marker.name, "object_destination_hash")
            .map_or_else(
                || {
                    let created = client.post_json(
                        "/api/markers",
                        json!({
                            "type": "marker",
                            "symbol": marker.symbol,
                            "name": marker.name,
                            "category": marker.category,
                            "lat": marker.lat,
                            "lon": marker.lon,
                            "notes": marker.notes
                        }),
                    )?;
                    summary.bump_created("markers");
                    text_field(&created, "object_destination_hash")
                },
                Ok,
            )?;
        client.put_json(
            &format!("/api/r3akt/missions/{MISSION_UID}/markers/{marker_id}"),
            json!({}),
        )?;
        summary.push_id("markers", marker_id);
    }
    let existing_zones = client.get_json("/api/zones")?;
    for zone in zones() {
        let zone_id = find_by_name(&existing_zones, zone.name, "zone_id").map_or_else(
            || {
                let created = client.post_json(
                    "/api/zones",
                    json!({ "name": zone.name, "points": zone.points }),
                )?;
                summary.bump_created("zones");
                text_field(&created, "zone_id")
            },
            Ok,
        )?;
        client.put_json(
            &format!("/api/r3akt/missions/{MISSION_UID}/zones/{zone_id}"),
            json!({}),
        )?;
        summary.push_id("zones", zone_id);
    }
    Ok(())
}

fn seed_checklists(
    client: &SarHttpClient,
    summary: &mut SarSeedSummary,
) -> Result<(), SarSeedError> {
    for template in checklist_templates() {
        client.post_json(
            "/checklists/templates",
            json!({
                "template": {
                    "uid": template.uid,
                    "template_name": template.name,
                    "description": template.description,
                    "created_by_team_member_rns_identity": "sar-ic-rns",
                    "columns": checklist_columns()
                }
            }),
        )?;
        summary.bump_upserted("checklist_templates");
    }
    for checklist in checklists() {
        client.post_json(
            "/checklists/offline",
            json!({
                "checklist_uid": checklist.uid,
                "mission_uid": MISSION_UID,
                "template_uid": checklist.template_uid,
                "origin_type": "BLANK_TEMPLATE",
                "name": checklist.name,
                "description": checklist.description,
                "created_by_team_member_rns_identity": "sar-ic-rns",
                "columns": checklist_columns()
            }),
        )?;
        summary.bump_upserted("checklists");
        summary.push_id("checklists", checklist.uid.clone());
        let tasks_to_seed = if checklist.uid == checklist_id("briefing") {
            checklist.tasks.iter().take(1).collect::<Vec<_>>()
        } else {
            Vec::new()
        };
        for (index, task) in tasks_to_seed.into_iter().enumerate() {
            let task_uid = format!("{}-task-{}", checklist.uid, index + 1);
            client.post_json(
                &format!("/checklists/{}/tasks", checklist.uid),
                json!({
                    "task_uid": task_uid,
                    "number": index + 1,
                    "notes": task,
                    "task_status": if index == 0 { "IN_PROGRESS" } else { "PENDING" },
                    "updated_by_team_member_rns_identity": "sar-ic-rns"
                }),
            )?;
            summary.bump_upserted("checklist_tasks");
        }
    }
    Ok(())
}

fn seed_assets_skills_assignments(
    client: &SarHttpClient,
    summary: &mut SarSeedSummary,
) -> Result<(), SarSeedError> {
    for asset in assets() {
        client.post_json(
            "/api/r3akt/assets",
            json!({
                "asset_uid": asset.uid,
                "team_member_uid": asset.team_member_uid,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "status": asset.status,
                "notes": asset.notes
            }),
        )?;
        summary.bump_upserted("assets");
        summary.push_id("assets", asset.uid);
    }
    for skill in skills() {
        client.post_json(
            "/api/r3akt/skills",
            json!({
                "skill_uid": skill.uid,
                "name": skill.name,
                "category": skill.category
            }),
        )?;
        summary.bump_upserted("skills");
    }
    for (member_identity, skill_uid, level) in member_skills() {
        client.post_json(
            "/api/r3akt/team-member-skills",
            json!({
                "team_member_rns_identity": member_identity,
                "skill_uid": skill_uid,
                "level": level
            }),
        )?;
        summary.bump_upserted("member_skills");
    }
    for requirement in task_skill_requirements() {
        client.post_json(
            "/api/r3akt/task-skill-requirements",
            json!({
                "task_uid": requirement.task_uid,
                "skill_uid": requirement.skill_uid,
                "minimum_level": requirement.minimum_level,
                "is_mandatory": true
            }),
        )?;
        summary.bump_upserted("task_skill_requirements");
    }
    for assignment in assignments() {
        client.post_json(
            "/api/r3akt/assignments",
            json!({
                "assignment_uid": assignment.uid,
                "mission_uid": MISSION_UID,
                "task_uid": assignment.task_uid,
                "team_member_rns_identity": assignment.member_rns_identity,
                "assigned_by": "sar-ic-rns",
                "status": assignment.status,
                "notes": assignment.notes,
                "assets": assignment.assets
            }),
        )?;
        summary.bump_upserted("assignments");
        summary.push_id("assignments", assignment.uid);
    }
    Ok(())
}

fn seed_eam(client: &SarHttpClient, summary: &mut SarSeedSummary) -> Result<(), SarSeedError> {
    for member in members() {
        client.post_json(
            "/api/EmergencyActionMessage",
            json!({
                "callsign": member.callsign,
                "team_member_uid": member.uid,
                "team_uid": member.team_uid,
                "reported_by": "SAR IC",
                "security_status": if member.team_uid == team_id("bravo") { "Yellow" } else { "Green" },
                "capability_status": if member.team_uid == team_id("medical") { "Green" } else { "Yellow" },
                "preparedness_status": "Green",
                "notes": format!("SAR scenario status snapshot for {}", member.display_name),
                "source": {
                    "rns_identity": member.rns_identity,
                    "display_name": member.display_name
                }
            }),
        )?;
        summary.bump_upserted("eam_messages");
    }
    Ok(())
}

fn seed_attachments(
    client: &SarHttpClient,
    summary: &mut SarSeedSummary,
) -> Result<(), SarSeedError> {
    let existing_files = client.get_json("/File")?;
    for attachment in attachments() {
        if let Some(file_id) = find_attachment(&existing_files, attachment.filename) {
            summary.bump_found("attachments");
            summary.push_id("attachments", file_id);
            continue;
        }
        let uploaded = client.upload_attachment(
            attachment.filename,
            attachment.media_type,
            &attachment.topic_id,
            attachment.content.as_bytes(),
        )?;
        let file_id = uploaded
            .get("FileID")
            .and_then(Value::as_u64)
            .map(|value| value.to_string())
            .ok_or_else(|| SarSeedError::MissingField("FileID".to_string()))?;
        summary.bump_created("attachments");
        summary.push_id("attachments", file_id);
    }
    Ok(())
}

fn seed_timeline(client: &SarHttpClient, summary: &mut SarSeedSummary) -> Result<(), SarSeedError> {
    for (index, entry) in narrative_timeline().iter().take(5).enumerate() {
        let uid = format!("{SCENARIO_ID}-change-{:02}", index + 1);
        client.post_json(
            "/api/r3akt/mission-changes",
            json!({
                "uid": uid,
                "mission_uid": MISSION_UID,
                "name": format!("SAR timeline {:02}", index + 1),
                "team_member_rns_identity": "sar-ic-rns",
                "notes": entry,
                "change_type": "ADD_CONTENT",
                "delta": {
                    "scenario_id": SCENARIO_ID,
                    "timeline_index": index + 1,
                    "narrative": entry
                }
            }),
        )?;
        client.post_json(
            "/api/r3akt/log-entries",
            json!({
                "entry_uid": format!("{SCENARIO_ID}-log-{:02}", index + 1),
                "mission_uid": MISSION_UID,
                "callsign": "SAR-IC",
                "content": entry,
                "keywords": ["sar", "spruce-ridge", "timeline"]
            }),
        )?;
        summary.bump_upserted("mission_changes");
        summary.bump_upserted("log_entries");
    }
    Ok(())
}

fn verify_major_objects(client: &SarHttpClient) -> Result<(), SarSeedError> {
    for path in [
        "/Status",
        "/Topic",
        "/api/markers",
        "/api/zones",
        "/checklists",
        "/api/EmergencyActionMessage",
        "/api/r3akt/events",
        &format!("/api/r3akt/missions/{MISSION_UID}?expand=all"),
    ] {
        client.get_json(path)?;
    }
    Ok(())
}

fn multipart_attachment_body(
    boundary: &str,
    filename: &str,
    media_type: &str,
    bytes: &[u8],
    sha256: &str,
    topic_id: &str,
) -> Vec<u8> {
    let mut body = Vec::new();
    for (name, value) in [
        ("category", "file"),
        ("sha256", sha256),
        ("topic_id", topic_id),
    ] {
        body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
        body.extend_from_slice(
            format!("Content-Disposition: form-data; name=\"{name}\"\r\n\r\n").as_bytes(),
        );
        body.extend_from_slice(value.as_bytes());
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
    body.extend_from_slice(
        format!("Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n")
            .as_bytes(),
    );
    body.extend_from_slice(format!("Content-Type: {media_type}\r\n\r\n").as_bytes());
    body.extend_from_slice(bytes);
    body.extend_from_slice(b"\r\n");
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}

fn find_by_name(payload: &Value, name: &str, id_field: &str) -> Option<String> {
    payload.as_array()?.iter().find_map(|row| {
        (row.get("name")
            .or_else(|| row.get("Name"))
            .and_then(Value::as_str)
            == Some(name))
        .then(|| {
            row.get(id_field)
                .and_then(Value::as_str)
                .map(ToOwned::to_owned)
        })
        .flatten()
    })
}

fn find_attachment(payload: &Value, filename: &str) -> Option<String> {
    payload.as_array()?.iter().find_map(|row| {
        (row.get("Name").and_then(Value::as_str) == Some(filename))
            .then(|| {
                row.get("FileID")
                    .and_then(Value::as_u64)
                    .map(|value| value.to_string())
            })
            .flatten()
    })
}

fn text_field(payload: &Value, field: &str) -> Result<String, SarSeedError> {
    payload
        .get(field)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .ok_or_else(|| SarSeedError::MissingField(field.to_string()))
}

fn topic_id(suffix: &str) -> String {
    format!("{SCENARIO_ID}.{suffix}")
}

fn team_id(suffix: &str) -> String {
    format!("{SCENARIO_ID}-team-{suffix}")
}

fn member_id(suffix: &str) -> String {
    format!("{SCENARIO_ID}-member-{suffix}")
}

fn checklist_id(suffix: &str) -> String {
    format!("{SCENARIO_ID}-checklist-{suffix}")
}

fn simulated_role(identity: &str) -> &'static str {
    match identity {
        "sar-ic-rns" => "Incident Command",
        "sar-alpha-rns" => "Alpha Ground",
        "sar-bravo-rns" => "Bravo Ground",
        "sar-comms-rns" => "Comms Relay",
        "sar-medic-rns" => "Medical",
        "sar-logistics-rns" => "Logistics",
        _ => "Observer",
    }
}

fn identities() -> [&'static str; 6] {
    [
        "sar-ic-rns",
        "sar-alpha-rns",
        "sar-bravo-rns",
        "sar-comms-rns",
        "sar-medic-rns",
        "sar-logistics-rns",
    ]
}

fn topics() -> Vec<(String, &'static str, &'static str)> {
    vec![
        (
            topic_id("command"),
            "SAR Command",
            "Incident command and objectives",
        ),
        (
            topic_id("search-teams"),
            "SAR Search Teams",
            "Field team coordination",
        ),
        (
            topic_id("medical"),
            "SAR Medical",
            "Medical standby and extraction",
        ),
        (
            topic_id("logistics"),
            "SAR Logistics",
            "Comms, vehicles, batteries, and staging",
        ),
        (
            topic_id("clues"),
            "SAR Clues",
            "Clue intake and probability updates",
        ),
    ]
}

#[derive(Clone)]
struct TeamSeed {
    uid: String,
    name: &'static str,
    color: &'static str,
    description: &'static str,
}

fn teams() -> Vec<TeamSeed> {
    vec![
        TeamSeed {
            uid: team_id("command"),
            name: "Command",
            color: "BLUE",
            description: "ICP, planning, safety, and operations control.",
        },
        TeamSeed {
            uid: team_id("alpha"),
            name: "Alpha Ground",
            color: "GREEN",
            description: "Drainage sweep from LKP to creek junction.",
        },
        TeamSeed {
            uid: team_id("bravo"),
            name: "Bravo Ground",
            color: "ORANGE",
            description: "Ridge contour and lookout spur search.",
        },
        TeamSeed {
            uid: team_id("medical"),
            name: "Medical",
            color: "RED",
            description: "Hypothermia treatment and extraction readiness.",
        },
        TeamSeed {
            uid: team_id("logistics"),
            name: "Logistics/Comms",
            color: "PURPLE",
            description: "Relay point, batteries, transport, and resource control.",
        },
    ]
}

#[derive(Clone)]
struct MemberSeed {
    uid: String,
    team_uid: String,
    rns_identity: &'static str,
    client_identity: &'static str,
    display_name: &'static str,
    callsign: &'static str,
    role: &'static str,
}

fn members() -> Vec<MemberSeed> {
    vec![
        MemberSeed {
            uid: member_id("ic"),
            team_uid: team_id("command"),
            rns_identity: "sar-ic-rns",
            client_identity: "sar-client-ic",
            display_name: "Incident Command",
            callsign: "SAR-IC",
            role: "HQ",
        },
        MemberSeed {
            uid: member_id("alpha-lead"),
            team_uid: team_id("alpha"),
            rns_identity: "sar-alpha-rns",
            client_identity: "sar-client-alpha",
            display_name: "Avery Stone",
            callsign: "ALPHA-1",
            role: "TEAM_LEAD",
        },
        MemberSeed {
            uid: member_id("bravo-lead"),
            team_uid: team_id("bravo"),
            rns_identity: "sar-bravo-rns",
            client_identity: "sar-client-bravo",
            display_name: "Mika Voss",
            callsign: "BRAVO-1",
            role: "TEAM_LEAD",
        },
        MemberSeed {
            uid: member_id("comms"),
            team_uid: team_id("logistics"),
            rns_identity: "sar-comms-rns",
            client_identity: "sar-client-comms",
            display_name: "Comms Relay",
            callsign: "COMMS-1",
            role: "RTO",
        },
        MemberSeed {
            uid: member_id("medic"),
            team_uid: team_id("medical"),
            rns_identity: "sar-medic-rns",
            client_identity: "sar-client-medic",
            display_name: "Medic Harper",
            callsign: "MED-1",
            role: "MEDIC",
        },
        MemberSeed {
            uid: member_id("logistics"),
            team_uid: team_id("logistics"),
            rns_identity: "sar-logistics-rns",
            client_identity: "sar-client-log",
            display_name: "Logistics Desk",
            callsign: "LOG-1",
            role: "HQ",
        },
    ]
}

#[derive(Clone)]
struct MarkerSeed {
    name: &'static str,
    symbol: &'static str,
    category: &'static str,
    lat: f64,
    lon: f64,
    notes: &'static str,
}

fn markers() -> Vec<MarkerSeed> {
    vec![
        MarkerSeed {
            name: "SAR Spruce Ridge ICP",
            symbol: "marker",
            category: "command",
            lat: 45.4246,
            lon: -63.5781,
            notes: "Incident command post at fire road gate.",
        },
        MarkerSeed {
            name: "SAR Spruce Ridge LKP",
            symbol: "marker",
            category: "clue",
            lat: 45.4312,
            lon: -63.5904,
            notes: "Trail register confirms last known point.",
        },
        MarkerSeed {
            name: "SAR Clue 1 Blue Fabric",
            symbol: "marker",
            category: "clue",
            lat: 45.4371,
            lon: -63.6032,
            notes: "Blue rain-shell fabric on alder branch.",
        },
        MarkerSeed {
            name: "SAR Clue 2 Boot Print",
            symbol: "marker",
            category: "clue",
            lat: 45.4418,
            lon: -63.6114,
            notes: "Boot print and trekking pole mark in mud.",
        },
        MarkerSeed {
            name: "SAR Drainage Hazard",
            symbol: "marker",
            category: "hazard",
            lat: 45.4446,
            lon: -63.6170,
            notes: "Steep wet drainage and radio shadow.",
        },
        MarkerSeed {
            name: "SAR Casualty Extraction Point",
            symbol: "marker",
            category: "medical",
            lat: 45.4479,
            lon: -63.6205,
            notes: "Subject located; litter extraction staged.",
        },
    ]
}

#[derive(Clone)]
struct ZoneSeed {
    name: &'static str,
    points: Vec<Value>,
}

fn zones() -> Vec<ZoneSeed> {
    vec![
        ZoneSeed {
            name: "SAR Staging Zone",
            points: points(&[
                (45.4229, -63.5800),
                (45.4260, -63.5790),
                (45.4253, -63.5746),
            ]),
        },
        ZoneSeed {
            name: "SAR Alpha Grid",
            points: points(&[
                (45.4310, -63.5920),
                (45.4380, -63.6040),
                (45.4340, -63.6080),
                (45.4284, -63.5968),
            ]),
        },
        ZoneSeed {
            name: "SAR Bravo Grid",
            points: points(&[
                (45.4375, -63.6045),
                (45.4460, -63.6155),
                (45.4430, -63.6210),
                (45.4350, -63.6100),
            ]),
        },
        ZoneSeed {
            name: "SAR High Risk Drainage",
            points: points(&[
                (45.4420, -63.6130),
                (45.4490, -63.6200),
                (45.4450, -63.6260),
                (45.4390, -63.6170),
            ]),
        },
        ZoneSeed {
            name: "SAR Medical LZ",
            points: points(&[
                (45.4484, -63.6220),
                (45.4502, -63.6204),
                (45.4492, -63.6178),
                (45.4475, -63.6196),
            ]),
        },
    ]
}

fn points(values: &[(f64, f64)]) -> Vec<Value> {
    values
        .iter()
        .map(|(lat, lon)| json!({ "lat": lat, "lon": lon }))
        .collect()
}

struct ChecklistTemplateSeed {
    uid: String,
    name: &'static str,
    description: &'static str,
}

fn checklist_templates() -> Vec<ChecklistTemplateSeed> {
    vec![
        ChecklistTemplateSeed {
            uid: format!("{SCENARIO_ID}-template-briefing"),
            name: "SAR Operational Briefing",
            description: "Objectives, hazards, comms, and safety briefing.",
        },
        ChecklistTemplateSeed {
            uid: format!("{SCENARIO_ID}-template-sortie"),
            name: "SAR Field Team Sortie",
            description: "Departure, sweep, clue handling, and return checks.",
        },
        ChecklistTemplateSeed {
            uid: format!("{SCENARIO_ID}-template-medical"),
            name: "SAR Medical Standby",
            description: "Hypothermia and extraction readiness.",
        },
        ChecklistTemplateSeed {
            uid: format!("{SCENARIO_ID}-template-comms"),
            name: "SAR Comms Relay",
            description: "Relay setup, radio checks, and message logging.",
        },
        ChecklistTemplateSeed {
            uid: format!("{SCENARIO_ID}-template-demob"),
            name: "SAR Demobilization",
            description: "Accountability, resource return, and final logs.",
        },
    ]
}

fn checklist_columns() -> Vec<Value> {
    vec![
        json!({ "column_name": "Due", "column_type": "RELATIVE_TIME", "column_editable": false, "is_removable": false, "system_key": "DUE_RELATIVE_DTG" }),
        json!({ "column_name": "Task", "column_type": "SHORT_STRING", "column_editable": true, "is_removable": false }),
        json!({ "column_name": "Owner", "column_type": "SHORT_STRING", "column_editable": true, "is_removable": false }),
        json!({ "column_name": "Asset", "column_type": "SHORT_STRING", "column_editable": true, "is_removable": true }),
    ]
}

struct ChecklistSeed {
    uid: String,
    template_uid: String,
    name: &'static str,
    description: &'static str,
    tasks: Vec<&'static str>,
}

fn checklists() -> Vec<ChecklistSeed> {
    vec![
        ChecklistSeed {
            uid: checklist_id("briefing"),
            template_uid: format!("{SCENARIO_ID}-template-briefing"),
            name: "OP 1 Briefing",
            description: "Night SAR briefing and risk controls.",
            tasks: vec![
                "Confirm LKP and hiker profile.",
                "Brief weather, drainage hazard, and radio shadow.",
                "Assign Alpha, Bravo, Medical, and Comms objectives.",
            ],
        },
        ChecklistSeed {
            uid: checklist_id("sortie-alpha"),
            template_uid: format!("{SCENARIO_ID}-template-sortie"),
            name: "Alpha Drainage Sortie",
            description: "Alpha sweep from LKP to drainage.",
            tasks: vec![
                "Depart ICP with radio and GPS check.",
                "Search creek crossing for trace evidence.",
                "Flag clue locations and report coordinates.",
            ],
        },
        ChecklistSeed {
            uid: checklist_id("medical"),
            template_uid: format!("{SCENARIO_ID}-template-medical"),
            name: "Medical Standby",
            description: "Hypothermia extraction readiness.",
            tasks: vec![
                "Stage med kit, blanket, and litter.",
                "Confirm LZ and extraction route.",
                "Prepare rewarming package.",
            ],
        },
        ChecklistSeed {
            uid: checklist_id("comms"),
            template_uid: format!("{SCENARIO_ID}-template-comms"),
            name: "Ridge Relay",
            description: "Radio relay on ridge knoll.",
            tasks: vec![
                "Set relay point above drainage.",
                "Check Alpha and Bravo radio traffic.",
                "Log clue and extraction traffic.",
            ],
        },
        ChecklistSeed {
            uid: checklist_id("demob"),
            template_uid: format!("{SCENARIO_ID}-template-demob"),
            name: "Demobilization",
            description: "Return and account for teams and assets.",
            tasks: vec![
                "Account for all field members.",
                "Recover radios, GPS, drone, and batteries.",
                "Close clue log and upload final resource manifest.",
            ],
        },
    ]
}

struct AssetSeed {
    uid: String,
    team_member_uid: String,
    name: &'static str,
    asset_type: &'static str,
    status: &'static str,
    notes: &'static str,
}

fn assets() -> Vec<AssetSeed> {
    vec![
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-radio-1"),
            team_member_uid: member_id("alpha-lead"),
            name: "VHF handheld radio A1",
            asset_type: "radio",
            status: "IN_USE",
            notes: "Alpha primary radio assigned to drainage sweep.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-gps-1"),
            team_member_uid: member_id("bravo-lead"),
            name: "GPS unit B1",
            asset_type: "gps",
            status: "IN_USE",
            notes: "Bravo track recorder assigned to ridge sweep.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-medkit"),
            team_member_uid: member_id("medic"),
            name: "Hypothermia med kit",
            asset_type: "medical",
            status: "AVAILABLE",
            notes: "Blankets, heat packs, vitals kit.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-litter"),
            team_member_uid: member_id("medic"),
            name: "Rescue litter",
            asset_type: "extraction",
            status: "AVAILABLE",
            notes: "Staged for drainage extraction.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-drone"),
            team_member_uid: member_id("logistics"),
            name: "Thermal drone",
            asset_type: "drone",
            status: "AVAILABLE",
            notes: "Observer-only due fog ceiling.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-vehicle"),
            team_member_uid: member_id("logistics"),
            name: "4x4 transport",
            asset_type: "vehicle",
            status: "AVAILABLE",
            notes: "Staged at fire road gate transport.",
        },
        AssetSeed {
            uid: format!("{SCENARIO_ID}-asset-battery"),
            team_member_uid: member_id("comms"),
            name: "Radio battery bank",
            asset_type: "power",
            status: "IN_USE",
            notes: "Assigned to relay power reserve.",
        },
    ]
}

struct SkillSeed {
    uid: String,
    name: &'static str,
    category: &'static str,
}

fn skills() -> Vec<SkillSeed> {
    vec![
        SkillSeed {
            uid: format!("{SCENARIO_ID}-skill-navigation"),
            name: "Navigation",
            category: "field",
        },
        SkillSeed {
            uid: format!("{SCENARIO_ID}-skill-first-aid"),
            name: "First Aid",
            category: "medical",
        },
        SkillSeed {
            uid: format!("{SCENARIO_ID}-skill-radio-relay"),
            name: "Radio Relay",
            category: "communications",
        },
        SkillSeed {
            uid: format!("{SCENARIO_ID}-skill-drone-observer"),
            name: "Drone Observer",
            category: "air",
        },
        SkillSeed {
            uid: format!("{SCENARIO_ID}-skill-tracking"),
            name: "Tracking",
            category: "field",
        },
    ]
}

fn member_skills() -> Vec<(&'static str, String, i64)> {
    vec![
        (
            "sar-alpha-rns",
            format!("{SCENARIO_ID}-skill-navigation"),
            4,
        ),
        ("sar-alpha-rns", format!("{SCENARIO_ID}-skill-tracking"), 3),
        (
            "sar-bravo-rns",
            format!("{SCENARIO_ID}-skill-navigation"),
            4,
        ),
        (
            "sar-comms-rns",
            format!("{SCENARIO_ID}-skill-radio-relay"),
            5,
        ),
        ("sar-medic-rns", format!("{SCENARIO_ID}-skill-first-aid"), 5),
        (
            "sar-logistics-rns",
            format!("{SCENARIO_ID}-skill-drone-observer"),
            3,
        ),
    ]
}

struct RequirementSeed {
    task_uid: String,
    skill_uid: String,
    minimum_level: i64,
}

fn task_skill_requirements() -> Vec<RequirementSeed> {
    vec![
        RequirementSeed {
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            skill_uid: format!("{SCENARIO_ID}-skill-tracking"),
            minimum_level: 2,
        },
        RequirementSeed {
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            skill_uid: format!("{SCENARIO_ID}-skill-first-aid"),
            minimum_level: 4,
        },
        RequirementSeed {
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            skill_uid: format!("{SCENARIO_ID}-skill-radio-relay"),
            minimum_level: 3,
        },
    ]
}

struct AssignmentSeed {
    uid: String,
    task_uid: String,
    member_rns_identity: &'static str,
    status: &'static str,
    notes: &'static str,
    assets: Vec<String>,
}

fn assignments() -> Vec<AssignmentSeed> {
    vec![
        AssignmentSeed {
            uid: format!("{SCENARIO_ID}-assignment-alpha-drainage"),
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            member_rns_identity: "sar-alpha-rns",
            status: "PENDING",
            notes: "Alpha works the creek crossing and drainage edge.",
            assets: vec![format!("{SCENARIO_ID}-asset-radio-1")],
        },
        AssignmentSeed {
            uid: format!("{SCENARIO_ID}-assignment-medical-lz"),
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            member_rns_identity: "sar-medic-rns",
            status: "PENDING",
            notes: "Medical confirms LZ and casualty packaging.",
            assets: vec![
                format!("{SCENARIO_ID}-asset-medkit"),
                format!("{SCENARIO_ID}-asset-litter"),
            ],
        },
        AssignmentSeed {
            uid: format!("{SCENARIO_ID}-assignment-comms-relay"),
            task_uid: format!("{}-task-1", checklist_id("briefing")),
            member_rns_identity: "sar-comms-rns",
            status: "PENDING",
            notes: "Comms establishes ridge relay.",
            assets: vec![format!("{SCENARIO_ID}-asset-battery")],
        },
    ]
}

struct AttachmentSeed {
    filename: &'static str,
    media_type: &'static str,
    topic_id: String,
    content: String,
}

fn attachments() -> Vec<AttachmentSeed> {
    vec![
        AttachmentSeed { filename: "sar-spruce-ridge-briefing.md", media_type: "text/markdown", topic_id: topic_id("command"), content: "# SAR - Spruce Ridge Missing Hiker\n\nOperational period begins at 18:30Z. LKP is the north trail register. Weather is cold rain and fog.\n".to_string() },
        AttachmentSeed { filename: "sar-spruce-ridge-comms-plan.csv", media_type: "text/csv", topic_id: topic_id("logistics"), content: "net,callsign,role,primary\ncommand,SAR-IC,incident command,VHF-1\nfield,ALPHA-1,drainage sweep,VHF-2\nfield,BRAVO-1,ridge sweep,VHF-2\nrelay,COMMS-1,radio relay,VHF-3\n".to_string() },
        AttachmentSeed { filename: "sar-spruce-ridge-clue-log.txt", media_type: "text/plain", topic_id: topic_id("clues"), content: "20:05 blue fabric near creek crossing\n21:10 boot print and trekking-pole mark above drainage\n21:35 subject located below drainage lip\n".to_string() },
        AttachmentSeed { filename: "sar-spruce-ridge-field-map.geojson", media_type: "application/geo+json", topic_id: topic_id("search-teams"), content: json!({"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"LKP"},"geometry":{"type":"Point","coordinates":[-63.5904,45.4312]}}]}).to_string() },
        AttachmentSeed { filename: "sar-spruce-ridge-resource-manifest.json", media_type: "application/json", topic_id: topic_id("logistics"), content: json!({"radios":1,"gps_units":1,"med_kits":1,"litters":1,"drone":1,"vehicles":1,"battery_banks":1}).to_string() },
    ]
}
