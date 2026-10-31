use super::{command_arg_text_with_position, command_topic_id, is_join_command_name, json};

pub(super) fn command_alias(command: &r3akt_protocol::Command) -> r3akt_protocol::Command {
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
    if result.name == "mission.nick"
        && let Some(nickname) =
            command_arg_text_with_position(&command.args, &["nickname", "nick", "name"], 0)
    {
        result.args["nickname"] = json!(nickname);
    }
    if result.name == "topic.subscribe"
        && let Some(topic) = command_topic_id(command)
    {
        result.args["topic_id"] = json!(topic);
    }
    result
}
