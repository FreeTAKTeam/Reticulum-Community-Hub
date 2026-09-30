use super::{Reader, TAK_PROTO_MAGIC_BYTE, TakConnectorError, XmlEvent};

/// Find one complete XML event using the XML parser's token boundaries, so a
/// closing-tag string inside a comment or CDATA section cannot end a frame.
pub(super) fn xml_frame_length(bytes: &[u8]) -> Result<Option<usize>, TakConnectorError> {
    if bytes.first() == Some(&TAK_PROTO_MAGIC_BYTE) {
        return Err(TakConnectorError::Receive(
            "inbound TAK protobuf frames are unsupported; configure XML CoT input (TAK_PROTO=0)"
                .to_string(),
        ));
    }
    let mut reader = Reader::from_reader(bytes);
    reader.config_mut().enable_all_checks(true);
    let mut depth = 0_usize;
    loop {
        match reader.read_event() {
            Ok(XmlEvent::Start(element)) => {
                if depth == 0 && element.name().as_ref() != b"event" {
                    return Err(TakConnectorError::Receive(
                        "CoT frame root must be event".to_string(),
                    ));
                }
                depth += 1;
            }
            Ok(XmlEvent::Empty(element)) if depth == 0 => {
                if element.name().as_ref() != b"event" {
                    return Err(TakConnectorError::Receive(
                        "CoT frame root must be event".to_string(),
                    ));
                }
                return usize::try_from(reader.buffer_position())
                    .map(Some)
                    .map_err(|error| TakConnectorError::Receive(error.to_string()));
            }
            Ok(XmlEvent::End(_)) => {
                depth = depth.checked_sub(1).ok_or_else(|| {
                    TakConnectorError::Receive("unmatched CoT closing tag".to_string())
                })?;
                if depth == 0 {
                    return usize::try_from(reader.buffer_position())
                        .map(Some)
                        .map_err(|error| TakConnectorError::Receive(error.to_string()));
                }
            }
            Ok(XmlEvent::DocType(_)) => {
                return Err(TakConnectorError::Receive(
                    "CoT document types are unsupported".to_string(),
                ));
            }
            Ok(XmlEvent::Text(text))
                if depth == 0 && !text.as_ref().iter().all(u8::is_ascii_whitespace) =>
            {
                return Err(TakConnectorError::Receive(
                    "unexpected data before CoT event".to_string(),
                ));
            }
            Ok(XmlEvent::Eof) | Err(quick_xml::Error::Syntax(_)) => return Ok(None),
            Ok(_) => {}
            Err(error) => {
                return Err(TakConnectorError::Receive(format!(
                    "malformed CoT XML: {error}"
                )));
            }
        }
    }
}

pub(super) fn take_frame(
    buffer: &mut Vec<u8>,
    max_bytes: usize,
) -> Result<Option<Vec<u8>>, TakConnectorError> {
    let padding = buffer
        .iter()
        .position(|byte| !byte.is_ascii_whitespace())
        .unwrap_or(buffer.len());
    buffer.drain(..padding);
    if buffer.is_empty() {
        return Ok(None);
    }
    if let Some(length) = xml_frame_length(buffer)? {
        if length > max_bytes {
            return Err(oversized(max_bytes));
        }
        return Ok(Some(buffer.drain(..length).collect()));
    }
    if buffer.len() > max_bytes {
        return Err(oversized(max_bytes));
    }
    Ok(None)
}

fn oversized(max_bytes: usize) -> TakConnectorError {
    TakConnectorError::Receive(format!("CoT frame exceeds {max_bytes} bytes"))
}
