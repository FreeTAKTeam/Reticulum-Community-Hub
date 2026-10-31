use super::*;

fn cot_marker_payload(uid: &str, lat: f64) -> Value {
    marker_payload_from_cot(&cot_marker_event(uid, lat))
}

fn cot_marker_event(uid: &str, lat: f64) -> TakInboundCotEvent {
    TakInboundCotEvent {
        sensor: None,
        sensor_diagnostic: None,
        version: "2.0".to_string(),
        uid: uid.to_string(),
        event_type: "a-f-G-U-C".to_string(),
        how: "m-g".to_string(),
        time: "2026-05-11T00:00:00Z".to_string(),
        start: "2026-05-11T00:00:00Z".to_string(),
        stale: "2026-05-11T00:10:00Z".to_string(),
        access: None,
        point: r3akt_tak_connector::TakInboundCotPoint {
            lat,
            lon: -63.0,
            hae: 12.0,
            ce: 5.0,
            le: 5.0,
        },
    }
}

#[test]
fn moving_uids_keep_separate_markers_across_bridge_restart_and_operator_rename() {
    use std::sync::atomic::AtomicUsize;
    let first = cot_marker_payload("peer-alpha", 45.0);
    let mut stored = first.clone();
    stored["object_destination_hash"] = json!("marker-alpha");
    stored["name"] = json!("Operator label");
    let token = marker_uid_token("peer-alpha");
    let distractors = vec![
        json!({"category": "other", "notes": token, "object_destination_hash": "wrong-category"}),
        json!({"category": "tak", "notes": format!("{token}extra"), "object_destination_hash": "wrong-token"}),
        json!({"category": "tak", "notes": format!("unrelated {token}"), "object_destination_hash": "wrong-position"}),
    ];
    let sequence = AtomicUsize::new(0);
    let (url, server) = crate::tests::spawn_rch_server(8, move |request| {
        assert!(
            request
                .to_ascii_lowercase()
                .contains("x-api-key: fixture-key")
        );
        match sequence.fetch_add(1, Ordering::SeqCst) {
            0 => {
                assert!(request.starts_with("GET /api/markers "));
                json!(distractors).to_string()
            }
            1 => {
                assert!(request.starts_with("POST /api/markers "));
                assert!(request.contains(r#""name":"peer-alpha""#));
                json!({"object_destination_hash": "marker-alpha"}).to_string()
            }
            2 | 4 => {
                assert!(request.starts_with("PATCH /api/markers/marker-alpha/position "));
                assert!(request.contains(r#""lat":46.0"#));
                json!({"status": "ok"}).to_string()
            }
            3 | 5 => {
                assert!(request.starts_with("GET /api/markers "));
                let mut markers = distractors.clone();
                markers.push(stored.clone());
                json!(markers).to_string()
            }
            6 => {
                assert!(request.starts_with("POST /api/markers "));
                assert!(request.contains(r#""name":"peer-bravo""#));
                json!({"object_destination_hash": "marker-bravo"}).to_string()
            }
            7 => {
                assert!(request.starts_with("PATCH /api/markers/marker-bravo/position "));
                json!({"status": "ok"}).to_string()
            }
            _ => panic!("unexpected request: {request}"),
        }
    });
    let client = RchNorthboundClient::new(&url, Some("fixture-key".to_string())).expect("client");
    let mut cache = (0..SEEN_CAPACITY)
        .map(|index| {
            (
                format!("old-peer-{index}"),
                CotMarker {
                    id: format!("old-marker-{index}"),
                    source_time: None,
                },
            )
        })
        .collect();
    apply_cot_marker(&client, "alpha:first", &first, &mut cache).expect("create alpha");
    assert_eq!(cache.len(), 1, "the marker cache stays bounded");
    let moved = cot_marker_payload("peer-alpha", 46.0);
    apply_cot_marker(&client, "alpha:moved", &moved, &mut cache).expect("move alpha");
    cache.clear();
    apply_cot_marker(&client, "alpha:restart", &moved, &mut cache).expect("recover alpha");
    let bravo = cot_marker_payload("peer-bravo", 47.0);
    apply_cot_marker(&client, "bravo:first", &bravo, &mut cache).expect("create bravo");
    apply_cot_marker(&client, "bravo:moved", &bravo, &mut cache).expect("move bravo");
    assert_eq!(cache["peer-alpha"].id, "marker-alpha");
    assert_eq!(cache["peer-bravo"].id, "marker-bravo");
    server.join().expect("server");
}

#[test]
fn lost_creation_reply_is_recovered_from_persisted_uid_without_another_post() {
    use std::io::Write;
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    let client = RchNorthboundClient::new(
        &format!("http://{}", listener.local_addr().expect("address")),
        None,
    )
    .expect("client");
    let server = thread::spawn(move || {
        let mut stored = Value::Null;
        for step in 0..4 {
            let (mut stream, _) = listener.accept().expect("accept");
            let request = crate::tests::read_http_request(&mut stream);
            let body = match step {
                0 => {
                    assert!(request.starts_with("GET /api/markers "));
                    json!([]).to_string()
                }
                1 => {
                    assert!(request.starts_with("POST /api/markers "));
                    stored = serde_json::from_str(request.split_once("\r\n\r\n").expect("body").1)
                        .expect("created marker");
                    stored["object_destination_hash"] = json!("committed-marker");
                    stream.write_all(b"HTTP/1.1 201 Created\r\nContent-Length: 100\r\nConnection: close\r\n\r\n").expect("lost response");
                    continue;
                }
                2 => {
                    assert!(request.starts_with("GET /api/markers "));
                    json!([stored]).to_string()
                }
                _ => {
                    assert!(request.starts_with("PATCH /api/markers/committed-marker/position "));
                    assert!(request.contains(r#""lat":46.0"#));
                    json!({"status": "ok"}).to_string()
                }
            };
            write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            )
            .expect("response");
        }
    });
    let mut cache = HashMap::new();
    assert!(
        apply_cot_marker(
            &client,
            "first",
            &cot_marker_payload("peer", 45.0),
            &mut cache
        )
        .is_err()
    );
    assert!(cache.is_empty());
    apply_cot_marker(
        &client,
        "next",
        &cot_marker_payload("peer", 46.0),
        &mut cache,
    )
    .expect("recover committed marker and apply movement");
    assert_eq!(cache["peer"].id, "committed-marker");
    server.join().expect("server");
}

#[test]
fn deleted_cached_marker_is_looked_up_again_and_recreated_on_retry() {
    use std::io::Write;
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    let client = RchNorthboundClient::new(
        &format!("http://{}", listener.local_addr().expect("address")),
        None,
    )
    .expect("client");
    let server = thread::spawn(move || {
        for (method, status, body) in [
            (
                "PATCH /api/markers/deleted/position ",
                "404 Not Found",
                "{}",
            ),
            ("GET /api/markers ", "200 OK", "[]"),
            (
                "POST /api/markers ",
                "201 Created",
                r#"{"object_destination_hash":"replacement"}"#,
            ),
        ] {
            let (mut stream, _) = listener.accept().expect("accept");
            let request = crate::tests::read_http_request(&mut stream);
            assert!(request.starts_with(method), "{request}");
            write!(
                stream,
                "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            )
            .expect("response");
        }
    });
    let mut state = BridgeState::default();
    state.cot_markers.insert(
        "peer".to_string(),
        CotMarker {
            id: "deleted".to_string(),
            source_time: None,
        },
    );
    state
        .pending_cot
        .push_back(("next-event".to_string(), cot_marker_payload("peer", 46.0)));
    assert!(flush_pending_cot(&client, &mut state).is_err());
    assert_eq!(state.pending_cot.len(), 1);
    assert!(state.cot_markers.is_empty());
    flush_pending_cot(&client, &mut state).expect("recreate deleted marker");
    assert!(state.pending_cot.is_empty());
    assert_eq!(state.cot_markers["peer"].id, "replacement");
    server.join().expect("server");
}

#[test]
fn marker_ids_cannot_change_the_position_request_path() {
    for id in [
        "",
        "marker/other",
        "marker?query",
        "marker#fragment",
        "../marker",
    ] {
        assert!(marker_identifier(&json!({"object_destination_hash": id})).is_err());
    }
}

#[test]
fn delayed_observations_do_not_move_markers_back_and_equal_time_updates_keep_metadata() {
    let stored = Arc::new(Mutex::new(Vec::<Value>::new()));
    let server_stored = Arc::clone(&stored);
    let (url, server) = crate::tests::spawn_rch_server(6, move |request| {
        let mut markers = server_stored.lock().expect("stored markers");
        if request.starts_with("GET /api/markers ") {
            return json!(*markers).to_string();
        }
        let payload: Value =
            serde_json::from_str(request.split_once("\r\n\r\n").expect("body").1).expect("payload");
        if request.starts_with("POST /api/markers ") {
            assert!(markers.is_empty(), "only one marker is created");
            markers.push(payload);
            markers[0]["object_destination_hash"] = json!("marker-alpha");
            markers[0]["name"] = json!("Operator rename");
            json!({"object_destination_hash": "marker-alpha"}).to_string()
        } else {
            assert!(request.starts_with("PATCH /api/markers/marker-alpha/position "));
            assert!(payload.get("name").is_none(), "preserve the operator name");
            for field in ["lat", "lon", "type", "symbol", "notes"] {
                markers[0][field] = payload[field].clone();
            }
            json!({"status": "ok"}).to_string()
        }
    });
    let client = RchNorthboundClient::new(&url, None).expect("client");
    let mut event = cot_marker_event("peer-alpha", 46.0);
    event.time = "2026-05-11T00:02:00Z".to_string();
    let mut cache = HashMap::new();
    apply_cot_marker(
        &client,
        "alpha:latest",
        &marker_payload_from_cot(&event),
        &mut cache,
    )
    .expect("create latest");
    event.time = "2026-05-11T00:01:00Z".to_string();
    event.point.lat = 45.0;
    let older = marker_payload_from_cot(&event);
    apply_cot_marker(&client, "alpha:old", &older, &mut cache).expect("ignore old");
    assert_eq!(stored.lock().expect("markers")[0]["lat"], json!(46.0));
    event.time = "2026-05-11T01:02:00+01:00".to_string();
    event.stale = "2026-05-11T00:20:00Z".to_string();
    event.event_type = "a-h-G-U-C".to_string();
    event.point.lat = 47.0;
    let equal = marker_payload_from_cot(&event);
    apply_cot_marker(&client, "alpha:equal-new-stale", &equal, &mut cache)
        .expect("equal time can update metadata");
    assert_eq!(stored.lock().expect("markers")[0]["symbol"], "hostile");
    event.time.clear();
    event.point.lat = 44.0;
    apply_cot_marker(
        &client,
        "alpha:undated",
        &marker_payload_from_cot(&event),
        &mut cache,
    )
    .expect("undated cannot replace dated observation");
    assert_eq!(stored.lock().expect("markers")[0]["lat"], json!(47.0));
    cache.clear();
    apply_cot_marker(&client, "alpha:old-after-restart", &older, &mut cache)
        .expect("durable source time rejects delayed event after restart");
    assert_eq!(stored.lock().expect("markers")[0]["lat"], json!(47.0));
    apply_cot_marker(&client, "alpha:equal-after-restart", &equal, &mut cache)
        .expect("equal observation can update after restart");
    let markers = stored.lock().expect("markers");
    assert_eq!(markers.len(), 1);
    assert_eq!(markers[0]["name"], "Operator rename");
    assert_eq!(markers[0]["type"], "hostile");
    assert_eq!(markers[0]["symbol"], "hostile");
    assert!(
        markers[0]["notes"]
            .as_str()
            .expect("notes")
            .contains("type=a-h-G-U-C")
    );
    server.join().expect("server");
}

#[test]
fn source_time_supports_legacy_markers_and_rejects_malformed_dates() {
    assert!(marker_source_time(&json!({"notes": "legacy marker"})).is_none());
    let mut event = cot_marker_event("legacy-peer", 45.0);
    event.time = "not-a-date".to_string();
    assert!(marker_source_time(&marker_payload_from_cot(&event)).is_none());
    event.time.clear();
    assert!(marker_source_time(&marker_payload_from_cot(&event)).is_none());
    event.time = "2026-05-11T00:00:00Z".to_string();
    assert!(marker_source_time(&marker_payload_from_cot(&event)).is_some());
}

#[test]
fn undated_legacy_markers_still_accept_undated_positions() {
    let (url, server) = crate::tests::spawn_rch_server(1, |request| {
        assert!(request.starts_with("PATCH /api/markers/legacy-marker/position "));
        assert!(request.contains(r#""lat":45.0"#));
        json!({"status": "ok"}).to_string()
    });
    let client = RchNorthboundClient::new(&url, None).expect("client");
    let mut cache = HashMap::from([(
        "legacy-peer".to_string(),
        CotMarker {
            id: "legacy-marker".to_string(),
            source_time: None,
        },
    )]);
    let mut event = cot_marker_event("legacy-peer", 45.0);
    event.time.clear();
    apply_cot_marker(
        &client,
        "legacy:next",
        &marker_payload_from_cot(&event),
        &mut cache,
    )
    .expect("undated observation");
    server.join().expect("server");
}
