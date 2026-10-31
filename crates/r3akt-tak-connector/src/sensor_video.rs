//! `CoT` endpoint candidates are local metadata; import never grants network disclosure.
use super::{BytesStart, Reader, XmlEvent, xml_attr};
use r3akt_map_core::sensor::{SensorManifest, VideoDescriptor};
pub(super) fn parse(raw: &str) -> (Option<VideoDescriptor>, Option<String>) {
    let mut reader = Reader::from_str(raw);
    let mut depth = 0usize;
    let mut detail = false;
    let mut result = None;
    loop {
        match reader.read_event() {
            Ok(XmlEvent::Start(element)) => {
                depth += 1;
                if depth == 2 {
                    detail = element.name().as_ref() == b"detail";
                }
                if depth == 3 && detail && element.name().as_ref() == b"__video" {
                    if result.is_some() {
                        return (None, Some("multiple CoT video candidates".into()));
                    }
                    result = Some(candidate(&reader, &element));
                }
            }
            Ok(XmlEvent::Empty(element))
                if depth == 2 && detail && element.name().as_ref() == b"__video" =>
            {
                if result.is_some() {
                    return (None, Some("multiple CoT video candidates".into()));
                }
                result = Some(candidate(&reader, &element));
            }
            Ok(XmlEvent::End(_)) => {
                if depth == 2 {
                    detail = false;
                }
                depth = depth.saturating_sub(1);
            }
            Ok(XmlEvent::Eof) => break,
            Err(_) => return (None, Some("invalid CoT video metadata".into())),
            _ => {}
        }
    }
    match result {
        Some(Ok(video)) => (video, None),
        Some(Err(error)) => (None, Some(error)),
        None => (None, None),
    }
}
fn candidate(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
) -> Result<Option<VideoDescriptor>, String> {
    let Some(url) = xml_attr(reader, element, b"url").map_err(|()| "invalid CoT video metadata")?
    else {
        return Ok(None);
    };
    let protocol = url
        .split_once("://")
        .ok_or("invalid CoT video reference")?
        .0
        .to_string();
    let video = VideoDescriptor {
        sensor_id: "cot-main".into(),
        protocol,
        endpoint_ref: url,
    };
    SensorManifest {
        sensor_id: "cot-main".into(),
        label: None,
        sensor_type: None,
        model: None,
        mount_id: None,
        intrinsics: None,
        video: Some(video.clone()),
    }
    .validate()
    .map_err(str::to_string)?;
    Ok(Some(video))
}
