use base64::{Engine as _, engine::general_purpose::STANDARD};
use r3akt_protocol::Payload;
use r3akt_transport_rns::reticulumd_message_to_payloads;
use serde_json::{Value, json};

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/columba_2_2_6.json")).unwrap()
}
fn message(fields: Value) -> Value {
    let f = fixture();
    let mut message = json!({"direction":"in","source":f["source"],"destination":f["destination"],
        "id":"synthetic-telemetry","timestamp":1_700_000_100});
    message["fields"] = fields;
    message
}
fn sample(fields: Value) -> r3akt_protocol::TelemetrySample {
    let decoded = reticulumd_message_to_payloads(
        &message(fields),
        fixture()["destination"].as_str().unwrap(),
    )
    .unwrap();
    let Payload::TelemetrySample(sample) = decoded.envelopes[0].payload.clone() else {
        panic!("telemetry")
    };
    sample
}
#[test]
fn actual_columba_codec_preserves_signed_altitude_and_bearing() {
    let s = sample(json!({"2":fixture()["packed_telemeter_b64"]}));
    assert_eq!(s.telemetry["location"]["altitude"], -12.5);
    assert_eq!(s.telemetry["location"]["bearing"], -1.5);
    assert_eq!(s.timestamp_s, Some(1_700_000_000));
    assert_eq!(
        s.packed_telemeter.unwrap(),
        STANDARD
            .decode(fixture()["packed_telemeter_b64"].as_str().unwrap())
            .unwrap()
    );
}
#[test]
fn pinned_daemon_location_projection_reaches_canonical_map_shape() {
    let f = fixture();
    let wire_hex = f["codec_frame"]["wire_hex"].as_str().unwrap();
    let wire: Vec<u8> = (0..wire_hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&wire_hex[i..i + 2], 16).unwrap())
        .collect();
    let inbound = lxmf::inbound_decode::decode_inbound_message(
        [0; 16],
        &wire,
        lxmf::inbound_decode::InboundPayloadMode::FullWire,
    )
    .unwrap();
    let fields = lxmf::wire_fields::rmpv_to_json(inbound.fields.as_ref().unwrap()).unwrap();
    assert_eq!(fields, f["daemon_fields"]);
    let s = sample(fields);
    assert_eq!(s.telemetry["location"]["latitude"], 0.0);
    assert_eq!(s.telemetry["location"]["altitude"], -12.5);
    assert_eq!(s.timestamp_s, Some(1_700_000_000));
    assert!(s.packed_telemeter.is_none());
}

fn event(stripped: bool) -> Value {
    let f = fixture();
    let hex = f["optional_frame"]["wire_hex"].as_str().unwrap();
    let mut m = message(json!({"2":{"lat":0.0,"lon":0.0,"alt":-12.5,"updated":1_700_000_000}}));
    m["id"] = f["optional_frame"]["id"].clone();
    json!({"message":m,"lxmf_bytes_hex":if stripped { &hex[32..] } else {hex}})
}
#[test]
fn journal_recovers_complete_packed_sensors_for_both_wire_framings() {
    for stripped in [false, true] {
        let decoded = r3akt_transport_rns::reticulumd_event_payload_to_payloads(
            &event(stripped),
            fixture()["destination"].as_str().unwrap(),
        )
        .unwrap();
        assert!(decoded.telemetry_diagnostics.is_empty());
        let Payload::TelemetrySample(sample) = &decoded.envelopes[0].payload else {
            panic!("telemetry")
        };
        assert_eq!(sample.telemetry["temperature"]["c"], 21.5);
        assert_eq!(sample.telemetry["200"]["synthetic"], true);
        assert_eq!(
            sample.packed_telemeter.as_ref().unwrap(),
            &STANDARD
                .decode(fixture()["optional_telemeter_b64"].as_str().unwrap())
                .unwrap()
        );
    }
}
#[test]
fn raw_frame_binding_failure_diagnoses_telemetry_and_keeps_valid_commands() {
    for corrupt in [
        "source",
        "id",
        "hex",
        "truncated",
        "absent-field",
        "destination",
    ] {
        let mut e = event(false);
        e["message"]["fields"]["9"] = json!([{"1":0}]);
        match corrupt {
            "source" => e["message"]["source"] = json!("11111111111111111111111111111111"),
            "destination" => {
                let mut hex = e["lxmf_bytes_hex"].as_str().unwrap().to_string();
                hex.replace_range(0..32, "11111111111111111111111111111111");
                e["lxmf_bytes_hex"] = json!(hex);
            }
            "id" => e["message"]["id"] = json!("wrong-synthetic-id"),
            "hex" => e["lxmf_bytes_hex"] = json!("not-hex"),
            "truncated" => e["lxmf_bytes_hex"] = json!("00"),
            "absent-field" => e["lxmf_bytes_hex"] = Value::Null,
            _ => unreachable!(),
        }
        let decoded = r3akt_transport_rns::reticulumd_event_payload_to_payloads(
            &e,
            fixture()["destination"].as_str().unwrap(),
        )
        .unwrap();
        assert_eq!(decoded.telemetry_diagnostics.len(), 1, "{corrupt}");
        assert_eq!(decoded.envelopes.len(), 1, "{corrupt}");
        assert!(matches!(decoded.envelopes[0].payload, Payload::Command(_)));
        let diagnostic = decoded.telemetry_diagnostics.join(";");
        assert!(diagnostic.contains("FIELD_TELEMETRY (0x02)"));
        assert!(
            !diagnostic.contains("wrong-synthetic-id")
                && !diagnostic.contains(fixture()["source"].as_str().unwrap())
        );
    }
}
#[test]
fn malformed_shapes_types_ranges_and_versions_are_explicit_and_chat_survives() {
    for payload in [
        json!({"1":true}),
        json!({"1":null}),
        json!({"1":253_402_300_800_u64}),
        json!({"2":[[],[],[],[],[],[],0]}),
        json!({"location":{"latitude":91.0,"longitude":0.0}}),
        json!({"location":{"latitude":"private-position","longitude":0.0}}),
        json!({"location":{"latitude":null,"longitude":0.0}}),
        json!({"schema_version":99,"sensors":{}}),
        json!({"schema_version":99,"location":{"latitude":0,"longitude":0}}),
        json!({"version":99,"lat":0,"lon":0}),
        json!([1, 2, 3]),
    ] {
        let mut m = message(json!({"2":payload}));
        m["content"] = json!("ordinary synthetic chat");
        let decoded =
            reticulumd_message_to_payloads(&m, fixture()["destination"].as_str().unwrap()).unwrap();
        assert_eq!(decoded.telemetry_diagnostics.len(), 1, "{payload}");
        assert_eq!(decoded.envelopes.len(), 1);
        assert!(matches!(
            decoded.envelopes[0].payload,
            Payload::TopicMessage(_)
        ));
        assert!(!decoded.telemetry_diagnostics[0].contains("private-position"));
    }
}
#[test]
fn bounded_parser_rejects_truncation_trailing_bytes_nonfinite_and_huge_lengths() {
    let good = STANDARD
        .decode(fixture()["packed_telemeter_b64"].as_str().unwrap())
        .unwrap();
    let mut trailing = good.clone();
    trailing.push(0);
    let mut deeply_nested = vec![0x91; 40];
    deeply_nested.push(0);
    let mut nonfinite = vec![0x81, 0x01, 0xcb];
    nonfinite.extend(f64::NAN.to_be_bytes());
    let mut cases = vec![
        trailing,
        deeply_nested,
        nonfinite,
        vec![0xdd, 255, 255, 255, 255],
        vec![0xdf, 255, 255, 255, 255],
        vec![0x82, 1, 0, 1, 1],
        vec![0x81, 0xc0, 0],
    ];
    for n in 0..good.len() {
        cases.push(good[..n].to_vec());
    }
    for bytes in cases {
        let decoded = reticulumd_message_to_payloads(
            &message(json!({"2":bytes})),
            fixture()["destination"].as_str().unwrap(),
        )
        .unwrap();
        assert_eq!(decoded.telemetry_diagnostics.len(), 1);
        assert!(decoded.envelopes.is_empty());
    }
    let decoded = reticulumd_message_to_payloads(
        &message(json!({"2":vec![0;1024*1024+1]})),
        fixture()["destination"].as_str().unwrap(),
    )
    .unwrap();
    assert!(decoded.telemetry_diagnostics[0].contains("limit exceeded"));
}
#[test]
fn optional_and_unknown_sensors_preserve_data_without_requiring_a_location() {
    let s = sample(
        json!({"FIELD_TELEMETRY":{"1":1_700_000_000,"2":null,"7":21.5,"200":{"synthetic":true}}}),
    );
    assert!(s.telemetry.get("location").is_none());
    assert_eq!(s.telemetry["temperature"]["c"], 21.5);
    assert_eq!(s.telemetry["200"]["synthetic"], true);
    assert!(s.packed_telemeter.is_none());
}
#[test]
fn raw_wire_payload_is_bounded_and_exact_before_upstream_decode() {
    let f = fixture();
    for stripped in [false, true] {
        let mut deep = event(stripped);
        deep["message"]["id"] = f["deep_frame"]["id"].clone();
        let hex = f["deep_frame"]["wire_hex"].as_str().unwrap();
        deep["lxmf_bytes_hex"] = json!(if stripped { &hex[32..] } else { hex });
        let mut trailing = event(stripped);
        trailing["lxmf_bytes_hex"] = json!(format!(
            "{}00",
            trailing["lxmf_bytes_hex"].as_str().unwrap()
        ));
        let mut enormous = event(stripped);
        let hex = enormous["lxmf_bytes_hex"].as_str().unwrap();
        let header = if stripped { 160 } else { 192 };
        enormous["lxmf_bytes_hex"] = json!(format!("{}ddffffffff", &hex[..header]));
        for e in [deep, trailing, enormous] {
            let d = r3akt_transport_rns::reticulumd_event_payload_to_payloads(
                &e,
                f["destination"].as_str().unwrap(),
            )
            .unwrap();
            assert_eq!(d.telemetry_diagnostics.len(), 1);
            assert!(d.envelopes.is_empty());
        }
    }
}
