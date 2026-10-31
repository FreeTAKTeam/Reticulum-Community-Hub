use super::{
    Reader, TakInboundCotEvent, XmlEvent, event_from_xml_start, point_from_xml_start, sensor_cot,
};

pub(crate) fn parse_inbound_cot_event(raw: &str) -> Option<TakInboundCotEvent> {
    let mut reader = Reader::from_str(raw);
    reader.config_mut().trim_text(true);
    let mut event: Option<TakInboundCotEvent> = None;
    let mut root_depth: Option<usize> = None;
    let mut depth = 0usize;
    let mut closed = false;
    let mut point_present = false;

    loop {
        match reader.read_event() {
            Ok(XmlEvent::Start(element)) => {
                if closed {
                    return None;
                }
                depth = depth.saturating_add(1);
                if event.is_none() {
                    event = Some(event_from_xml_start(&reader, &element)?);
                    root_depth = Some(depth);
                } else if root_depth.is_some_and(|root| depth == root + 1)
                    && element.name().as_ref() == b"point"
                    && let Some(parsed_event) = event.as_mut()
                {
                    parsed_event.point = point_from_xml_start(&reader, &element)?;
                    point_present = true;
                }
            }
            Ok(XmlEvent::Empty(element)) => {
                if closed {
                    return None;
                }
                if depth == 0 {
                    closed = true;
                }
                let element_depth = depth.saturating_add(1);
                if event.is_none() {
                    event = Some(event_from_xml_start(&reader, &element)?);
                    root_depth = Some(element_depth);
                } else if root_depth.is_some_and(|root| element_depth == root + 1)
                    && element.name().as_ref() == b"point"
                    && let Some(parsed_event) = event.as_mut()
                {
                    parsed_event.point = point_from_xml_start(&reader, &element)?;
                    point_present = true;
                }
            }
            Ok(XmlEvent::End(_)) => {
                depth = depth.checked_sub(1)?;
                if depth == 0 {
                    closed = true;
                }
            }
            Ok(XmlEvent::DocType(_)) | Err(_) => return None,
            Ok(XmlEvent::Text(text))
                if depth == 0 && !text.as_ref().iter().all(u8::is_ascii_whitespace) =>
            {
                return None;
            }
            Ok(XmlEvent::Eof) => break,
            Ok(_) => {}
        }
    }

    if closed && depth == 0 {
        if let Some(event) = event.as_mut() {
            match sensor_cot::parse(raw, &event.time, &event.stale) {
                Ok(sensor) if point_present => event.sensor = sensor,
                Ok(Some(_)) => event.sensor_diagnostic = Some("sensor origin point missing".into()),
                Ok(None) => {}
                Err(reason) => event.sensor_diagnostic = Some(reason),
            }
        }
        event
    } else {
        None
    }
}
