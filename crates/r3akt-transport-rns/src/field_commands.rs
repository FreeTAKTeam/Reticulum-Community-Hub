use r3akt_protocol::Command;
use serde_json::{Map, Value};

#[derive(Debug, PartialEq)]
pub(crate) enum DirectLxmfCommandResult {
    Valid(Command),
    Malformed(String),
    Unsupported,
}

pub(crate) fn direct_lxmf_commands(
    fields: Option<&Map<String, Value>>,
) -> Vec<DirectLxmfCommandResult> {
    let Some(commands) =
        fields.and_then(|fields| field_value(fields, &["9", "0x09", "FIELD_COMMANDS"]))
    else {
        return Vec::new();
    };
    match commands {
        Value::Array(commands) if commands.is_empty() => vec![DirectLxmfCommandResult::Malformed(
            "field 0x09 command list is empty".into(),
        )],
        Value::Array(commands) if commands.len() > 256 => vec![DirectLxmfCommandResult::Malformed(
            "field 0x09 exceeds 256 command entries".into(),
        )],
        Value::Array(commands) => commands.iter().map(parse_command).collect(),
        command => vec![parse_command(command)],
    }
}

fn parse_command(command: &Value) -> DirectLxmfCommandResult {
    let Some(command) = command.as_object() else {
        return DirectLxmfCommandResult::Malformed(
            "field 0x09 command entry must be an object".to_string(),
        );
    };
    if let Some(request) = command.get("1").or_else(|| command.get("0x01")) {
        if ["command_type", "Command", "0", "t"]
            .iter()
            .any(|key| command.contains_key(*key))
        {
            return DirectLxmfCommandResult::Malformed(
                "ambiguous application command selectors".into(),
            );
        }
        return telemetry_request(request, command);
    }
    let selector = if command.contains_key("command_type") {
        "command_type"
    } else if command.contains_key("Command") {
        "Command"
    } else if command.contains_key("0") {
        "0"
    } else {
        // REM's compact t/a dialect and unknown numeric application commands are
        // valid application metadata, but are not mission-envelope selectors.
        return if command.contains_key("t") || command.keys().any(|key| key.parse::<u8>().is_ok()) {
            DirectLxmfCommandResult::Unsupported
        } else {
            DirectLxmfCommandResult::Malformed(
                "field 0x09 command entry has no recognized selector".into(),
            )
        };
    };
    let Some(name) = command
        .get(selector)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
    else {
        return DirectLxmfCommandResult::Malformed(format!(
            "field 0x09 selector {selector:?} must be a non-empty string"
        ));
    };
    if selector == "command_type" && command.get("args").is_some_and(|args| !args.is_object()) {
        return DirectLxmfCommandResult::Malformed("mission command args must be an object".into());
    }
    let correlation_id = command
        .get("command_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string);
    let args = if matches!(selector, "Command" | "0") {
        let mut args = Map::new();
        if let Some(Value::Object(explicit_args)) = command.get("args") {
            args.extend(explicit_args.clone());
        } else if let Some(explicit_args) = command.get("args") {
            args.insert("args".to_string(), explicit_args.clone());
        }
        for (key, value) in command {
            if !matches!(key.as_str(), "Command" | "0" | "command_id" | "args") {
                args.insert(key.clone(), value.clone());
            }
        }
        Value::Object(args)
    } else {
        command
            .get("args")
            .cloned()
            .filter(Value::is_object)
            .unwrap_or_else(|| serde_json::json!({}))
    };
    DirectLxmfCommandResult::Valid(Command {
        name: name.to_string(),
        args,
        correlation_id,
    })
}

fn telemetry_request(request: &Value, command: &Map<String, Value>) -> DirectLxmfCommandResult {
    let timebase = match request {
        Value::Array(values) if values.len() == 2 && values[1].is_boolean() => &values[0],
        Value::Array(_) => {
            return DirectLxmfCommandResult::Malformed(
                "telemetry request must be [seconds, boolean]".into(),
            );
        }
        value => value,
    };
    // Python compatibility truncates fractional Unix seconds. Booleans/strings
    // are not numbers; reject negatives and values outside Python datetime's supported year range.
    let Some(seconds) = timebase
        .as_f64()
        .filter(|v| v.is_finite() && *v >= 0.0 && *v < 253_402_300_800.0)
    else {
        return DirectLxmfCommandResult::Malformed(
            "telemetry request seconds must be a non-negative numeric Unix time".into(),
        );
    };
    let seconds = format!("{:.0}", seconds.trunc()).parse::<i64>();
    let Ok(seconds) = seconds else {
        return DirectLxmfCommandResult::Malformed(
            "telemetry request seconds are out of range".into(),
        );
    };
    let mut args = serde_json::json!({"since":seconds});
    if let Some(topic) = field_value(command, &["TopicID", "topic_id", "topic", "Topic"]) {
        let Some(topic) = topic.as_str().map(str::trim).filter(|s| !s.is_empty()) else {
            return DirectLxmfCommandResult::Malformed(
                "telemetry request topic must be a non-empty string".into(),
            );
        };
        args["topic_id"] = Value::String(topic.into());
    }
    DirectLxmfCommandResult::Valid(Command {
        name: "telemetry.collect".into(),
        args,
        correlation_id: None,
    })
}

fn field_value<'a>(fields: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().find_map(|key| {
        fields.get(*key).or_else(|| {
            fields
                .iter()
                .find(|(candidate, _)| candidate.eq_ignore_ascii_case(key))
                .map(|(_, value)| value)
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn collector_dialect_fixtures_inspect_every_entry_without_private_values() {
        let cases: Vec<Value> =
            serde_json::from_str(include_str!("../tests/fixtures/collector_requests.json"))
                .unwrap();
        for case in cases {
            let parsed = direct_lxmf_commands(case["fields"].as_object());
            let valid = parsed
                .iter()
                .filter(|r| matches!(r, DirectLxmfCommandResult::Valid(_)))
                .count();
            assert_eq!(
                valid,
                usize::try_from(case["commands"].as_u64().unwrap()).unwrap(),
                "{}",
                case["name"]
            );
            assert_eq!(
                parsed.len() - valid,
                usize::try_from(case["diagnostics"].as_u64().unwrap()).unwrap(),
                "{}",
                case["name"]
            );
            assert!(!format!("{parsed:?}").contains("private-value"));
        }
    }
    #[test]
    fn fractional_time_and_topic_follow_python_compatibility() {
        let fields = serde_json::json!({"9":[{"1":[1_700_000_000.75,false],"TopicID":"ops"}]});
        let parsed = direct_lxmf_commands(fields.as_object());
        let DirectLxmfCommandResult::Valid(command) = &parsed[0] else {
            panic!("valid request");
        };
        assert_eq!(command.name, "telemetry.collect");
        assert_eq!(
            command.args,
            serde_json::json!({"since":1_700_000_000,"topic_id":"ops"})
        );
    }
}
