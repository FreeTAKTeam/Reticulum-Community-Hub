use super::*;
use serde_json::json;

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn binary_slot(bytes: &[u8]) -> Vec<u8> {
    let mut slot = vec![0xc5];
    slot.extend_from_slice(&u16::try_from(bytes.len()).unwrap().to_be_bytes());
    slot.extend_from_slice(bytes);
    slot
}

#[test]
fn issue_307_count_is_rejected_before_allocation() {
    // Same claimed count and lengths as the private production records, no peer data.
    for size in [5, 101, 102] {
        let mut bytes = vec![0xdd, 0x41, 0xdc, 0xc1, 0x48];
        bytes.resize(size, 0);
        assert_eq!(decode(&bytes), Err(DecodeError::Items));
        assert!(decode_hex(&hex(&bytes)).is_empty());
    }
    for bytes in [
        [0xdd, 0xff, 0xff, 0xff, 0xff],
        [0xdf, 0xff, 0xff, 0xff, 0xff],
        [0xc6, 0xff, 0xff, 0xff, 0xff],
        [0xdb, 0xff, 0xff, 0xff, 0xff],
    ] {
        assert!(decode(&bytes).is_err());
    }
}

#[test]
fn rejects_encoded_and_decoded_byte_limits_before_parsing() {
    assert_eq!(
        decode(&vec![b'a'; MAX_APP_DATA_BYTES + 1]),
        Err(DecodeError::TooLarge)
    );
    assert_eq!(
        decode_hex_result(&"aa".repeat(MAX_APP_DATA_BYTES + 1)),
        Err(DecodeError::TooLarge)
    );
    assert_eq!(
        decode_hex_result(&" ".repeat(MAX_APP_DATA_BYTES * 2 + 1)),
        Err(DecodeError::TooLarge)
    );
    assert_eq!(decode_hex_result("zz"), Err(DecodeError::Hex));
    assert_eq!(decode_hex_result("a"), Err(DecodeError::Hex));
    assert_eq!(decode_hex_result("  "), Ok(Vec::new()));
    assert_eq!(decode_hex_result(" 7233616b74 "), Ok(vec!["r3akt".into()]));
    assert!(decode(&vec![b'a'; MAX_APP_DATA_BYTES]).is_ok());
}

#[test]
fn all_fixed_width_scalars_require_their_complete_payload() {
    for (marker, length) in [
        (0xcc, 1),
        (0xcd, 2),
        (0xce, 4),
        (0xcf, 8),
        (0xd0, 1),
        (0xd1, 2),
        (0xd2, 4),
        (0xd3, 8),
        (0xca, 4),
        (0xcb, 8),
        (0xd4, 2),
        (0xd5, 3),
        (0xd6, 5),
        (0xd7, 9),
        (0xd8, 17),
    ] {
        let mut bytes = vec![0x91, marker];
        bytes.resize(2 + length, 0);
        assert!(msgpack::validate(&bytes).is_ok(), "marker {marker:x}");
        for end in 0..bytes.len() {
            assert!(
                msgpack::validate(&bytes[..end]).is_err(),
                "marker {marker:x}, end {end}"
            );
            assert!(decode_hex(&hex(&bytes[..end])).is_empty());
        }
    }
}

#[test]
fn containers_strings_binary_extensions_and_trailing_data_are_checked() {
    for bytes in [
        vec![0xdc, 0, 1, 0xc0],
        vec![0xdd, 0, 0, 0, 1, 0xc0],
        vec![0xde, 0, 1, 0xc0, 0xc0],
        vec![0xdf, 0, 0, 0, 1, 0xc0, 0xc0],
        vec![0xd9, 1, b'x'],
        vec![0xda, 0, 1, b'x'],
        vec![0xdb, 0, 0, 0, 1, b'x'],
        vec![0xc4, 1, 0],
        vec![0xc5, 0, 1, 0],
        vec![0xc6, 0, 0, 0, 1, 0],
        vec![0xc7, 1, 0, 0],
        vec![0xc8, 0, 1, 0, 0],
        vec![0xc9, 0, 0, 0, 1, 0, 0],
    ] {
        assert!(msgpack::validate(&bytes).is_ok());
        for end in 0..bytes.len() {
            assert!(msgpack::validate(&bytes[..end]).is_err());
        }
        let mut trailing = bytes;
        trailing.push(0xc0);
        assert_eq!(msgpack::validate(&trailing), Err(DecodeError::Malformed));
    }
    assert_eq!(msgpack::validate(&[0xc1]), Err(DecodeError::Malformed));
}

#[test]
fn depth_and_total_items_have_explicit_boundaries() {
    let mut deep = vec![0x91; MAX_DEPTH];
    deep.push(0xc0);
    assert!(msgpack::validate(&deep).is_ok());
    deep.insert(0, 0x91);
    assert_eq!(msgpack::validate(&deep), Err(DecodeError::Depth));
    let mut broad = vec![0xdc, 0x0f, 0xff];
    broad.extend(std::iter::repeat_n(0xc0, MAX_ITEMS - 1));
    assert!(msgpack::validate(&broad).is_ok());
    broad[1..3].copy_from_slice(&[0x10, 0]);
    broad.push(0xc0);
    assert_eq!(msgpack::validate(&broad), Err(DecodeError::Items));
}

#[test]
fn preserves_supported_plain_map_string_and_embedded_formats() {
    let expected = vec!["r3akt".to_owned(), "group_chat".to_owned()];
    assert_eq!(decode(b"R3AKT;Group_Chat").unwrap(), expected);
    let caps = json!({"caps": ["R3AKT", "group_chat"]});
    let packed = rmp_serde::to_vec_named(&caps).unwrap();
    assert_eq!(decode(&packed).unwrap(), expected);
    assert_eq!(
        decode(&rmp_serde::to_vec("r3akt").unwrap()).unwrap(),
        vec!["r3akt"]
    );
    assert_eq!(
        decode(&rmp_serde::to_vec_named(&json!(["peer", 3, caps])).unwrap()).unwrap(),
        expected
    );
    let mut binary = vec![0x93, 0xc0, 0xc0];
    binary.extend(binary_slot(&packed));
    assert_eq!(decode(&binary).unwrap(), expected);
    let array = rmp_serde::to_vec(&json!([null, null, packed])).unwrap();
    assert_eq!(decode(&array).unwrap(), expected);
    assert_eq!(
        decode_hex(
            "93c409416c7068612052454d03c42f83a3617070a3726368a6736368656d6101a46361707392a55233414b54b1456d657267656e63794d65737361676573"
        ),
        vec!["r3akt", "emergencymessages"]
    );
}

#[test]
fn embedded_bad_documents_cannot_bypass_validation_or_hide_later_capabilities() {
    for bad in [
        vec![0xdd, 0x41, 0xdc, 0xc1, 0x48],
        vec![0x91, 0xd3],
        [vec![0x91; MAX_DEPTH + 1], vec![0xc0]].concat(),
    ] {
        assert!(decode_slot(&binary_slot(&bad)).is_err());
        assert!(decode_slot(&rmp_serde::to_vec(&bad).unwrap()).is_err());
        let mut array = vec![0x94, 0xc0, 0xc0];
        array.extend(binary_slot(&bad));
        array.extend(rmp_serde::to_vec_named(&json!({"caps": ["r3akt"]})).unwrap());
        assert_eq!(decode(&array).unwrap(), vec!["r3akt"]);
    }
}

#[test]
fn arbitrary_short_headers_never_panic() {
    for marker in 0..=255_u8 {
        for length in 1..=12 {
            let mut input = vec![0xff; length];
            input[0] = marker;
            // Validation uses no heap allocation based on any declared count.
            let _ = msgpack::validate(&input);
        }
    }
}

#[test]
fn opaque_optional_slots_do_not_count_as_failed_announces() {
    let rejections = Rejections::default();
    let opaque = [0xdd, 0x41, 0xdc, 0xc1, 0x48];
    let mut array = vec![0x94, 0xc0, 0xc0];
    array.extend(binary_slot(&opaque));
    array.extend(rmp_serde::to_vec(&opaque.to_vec()).unwrap());
    assert!(decode_hex_with_rejections(&hex(&array), &rejections).is_empty());
    assert_eq!(rejections.total.load(Ordering::Relaxed), 0);

    // Several unrelated slots before real capabilities must remain a success.
    array[0] = 0x95;
    array.extend(rmp_serde::to_vec_named(&json!({"caps": ["r3akt"]})).unwrap());
    assert_eq!(
        decode_hex_with_rejections(&hex(&array), &rejections),
        vec!["r3akt"]
    );
    assert_eq!(rejections.total.load(Ordering::Relaxed), 0);

    // A malformed outer document counts once, regardless of its slot contents.
    array.push(0xc0);
    for (index, input) in [hex(&array), hex(&opaque), "zz".to_owned()]
        .iter()
        .enumerate()
    {
        assert!(decode_hex_with_rejections(input, &rejections).is_empty());
        assert_eq!(rejections.total.load(Ordering::Relaxed), (index + 1) as u64);
    }
}

#[test]
fn rejection_logging_resumes_by_time_even_after_large_counts_or_idle_periods() {
    let rejections = Rejections::default();
    assert_eq!(rejections.record_at(0), Some(1));
    for _ in 0..100 {
        assert_eq!(rejections.record_at(0), None);
    }
    assert_eq!(rejections.record_at(LOG_INTERVAL_SECONDS - 1), None);
    assert_eq!(rejections.record_at(LOG_INTERVAL_SECONDS), Some(103));
    rejections.total.store(1_000_000, Ordering::Relaxed);
    assert_eq!(rejections.record_at(86_400), Some(1_000_001));
    assert_eq!(rejections.record_at(86_400), None);
    assert_eq!(
        rejections.record_at(86_400 + LOG_INTERVAL_SECONDS),
        Some(1_000_003)
    );
}

#[test]
fn concurrent_rejections_share_one_log_window_without_losing_counts() {
    let rejections = Rejections::default();
    let barrier = std::sync::Barrier::new(16);
    std::thread::scope(|scope| {
        let handles: Vec<_> = (0..16)
            .map(|_| {
                scope.spawn(|| {
                    barrier.wait();
                    rejections.record_at(100).is_some()
                })
            })
            .collect();
        let logged = handles
            .into_iter()
            .map(|handle| usize::from(handle.join().unwrap()))
            .sum::<usize>();
        assert_eq!(logged, 1);
    });
    assert_eq!(rejections.total.load(Ordering::Relaxed), 16);
    assert_eq!(rejections.record_at(100 + LOG_INTERVAL_SECONDS), Some(17));
}
