"""Text-building helpers for command responses."""

from __future__ import annotations

import json
from typing import Any, List

from reticulum_telemetry_hub.api.models import FileAttachment, Subscriber, Topic
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)


def build_help_text(command_manager: Any) -> str:
    """Assemble a Markdown list of supported commands for LXMF clients.

    Args:
        command_manager (Any): An object exposing the command name constants.

    Returns:
        str: Markdown-formatted list of supported commands.
    """

    command_names = command_manager._all_command_names()  # noqa: SLF001
    lines = [
        "# Command list",
        "",
        "Use the `Command` field (`0`) to choose an action when building payloads.",
        "",
        "## Supported commands",
    ]
    for command_name in command_names:
        lines.append(f"- `{command_name}`")
    lines.append("- `TelemetryRequest` (`1`)")
    return "\n".join(lines)


def build_examples_text(command_manager: Any) -> str:
    """Assemble Markdown examples for LXMF clients.

    Args:
        command_manager (Any): An object exposing the command name constants.

    Returns:
        str: Markdown-formatted description and payload examples for commands.
    """

    lines = [
        "# Command examples",
        "",
        "Use the `Command` field (`0`) to choose an action when building payloads.",
        "",
        "## Examples",
    ]
    for entry in command_reference(command_manager):
        lines.append(f"- **{entry['title']}**")
        lines.append(f"  - Description: {entry['description']}")
        lines.append(f"  - Example: `{entry['example']}`")
    telemetry_example = _telemetry_request_example()
    lines.append("- **TelemetryRequest (numeric key `1`)**")
    lines.append(
        "  - Description: Request telemetry snapshots using the `TelemetryRequest` numeric key."
    )
    lines.append(
        "  - Example: `"
        f"{telemetry_example}"
        "` (timestamp = earliest UNIX time to include)"
    )
    return "\n".join(lines)


def _telemetry_request_example() -> str:
    """Return an example telemetry request payload."""

    return json.dumps(
        {str(TelemetryController.TELEMETRY_REQUEST): "<unix timestamp>"},
        sort_keys=True,
    )


def command_reference(command_manager: Any) -> List[dict]:
    """Return the command reference entries used by help text generation.

    Args:
        command_manager (Any): An object exposing the command name constants.

    Returns:
        List[dict]: Descriptions and examples for supported commands.
    """

    def example(command: str, **fields: Any) -> str:
        payload = {"Command": command}
        payload.update(fields)
        return json.dumps(payload, sort_keys=True)

    return [
        {
            "title": command_manager.CMD_JOIN,
            "description": "Register your LXMF destination with the hub to receive replies.",
            "example": example(command_manager.CMD_JOIN),
        },
        {
            "title": command_manager.CMD_LEAVE,
            "description": "Remove your destination from the hub's connection list.",
            "example": example(command_manager.CMD_LEAVE),
        },
        {
            "title": command_manager.CMD_LIST_CLIENTS,
            "description": "List LXMF destinations currently joined to the hub.",
            "example": example(command_manager.CMD_LIST_CLIENTS),
        },
        {
            "title": command_manager.CMD_GET_APP_INFO,
            "description": (
                "Return the app name, version, and description from config.ini."
            ),
            "example": example(command_manager.CMD_GET_APP_INFO),
        },
        {
            "title": command_manager.CMD_LIST_FILES,
            "description": "List stored file attachments saved on the hub.",
            "example": example(command_manager.CMD_LIST_FILES),
        },
        {
            "title": command_manager.CMD_LIST_IMAGES,
            "description": "List stored image attachments saved on the hub.",
            "example": example(command_manager.CMD_LIST_IMAGES),
        },
        {
            "title": command_manager.CMD_LIST_TOPIC,
            "description": "Display every registered topic and its ID.",
            "example": example(command_manager.CMD_LIST_TOPIC),
        },
        {
            "title": command_manager.CMD_CREATE_TOPIC,
            "description": "Create a topic by providing a name and path.",
            "example": example(
                command_manager.CMD_CREATE_TOPIC,
                TopicName="Weather",
                TopicPath="environment/weather",
            ),
        },
        {
            "title": command_manager.CMD_RETRIEVE_FILE,
            "description": (
                "Retrieve a stored file by FileID. The hub responds with metadata and "
                "includes the file bytes in FIELD_FILE_ATTACHMENTS."
            ),
            "example": example(command_manager.CMD_RETRIEVE_FILE, FileID="<FileID>"),
        },
        {
            "title": command_manager.CMD_RETRIEVE_IMAGE,
            "description": (
                "Retrieve a stored image by FileID. The hub responds with metadata and "
                "includes the image bytes in FIELD_IMAGE."
            ),
            "example": example(command_manager.CMD_RETRIEVE_IMAGE, FileID="<FileID>"),
        },
        {
            "title": command_manager.CMD_RETRIEVE_TOPIC,
            "description": "Fetch a specific topic by TopicID.",
            "example": example(command_manager.CMD_RETRIEVE_TOPIC, TopicID="<TopicID>"),
        },
        {
            "title": command_manager.CMD_DELETE_TOPIC,
            "description": "Delete a topic (and unsubscribe listeners).",
            "example": example(command_manager.CMD_DELETE_TOPIC, TopicID="<TopicID>"),
        },
        {
            "title": command_manager.CMD_PATCH_TOPIC,
            "description": "Update fields on a topic by TopicID.",
            "example": example(
                command_manager.CMD_PATCH_TOPIC,
                TopicID="<TopicID>",
                TopicDescription="New description",
            ),
        },
        {
            "title": command_manager.CMD_SUBSCRIBE_TOPIC,
            "description": "Subscribe the sending destination to a topic.",
            "example": example(
                command_manager.CMD_SUBSCRIBE_TOPIC,
                TopicID="<TopicID>",
                Metadata={"tag": "field-station"},
            ),
        },
        {
            "title": command_manager.CMD_LIST_SUBSCRIBER,
            "description": "List every subscriber registered with the hub.",
            "example": example(command_manager.CMD_LIST_SUBSCRIBER),
        },
        {
            "title": f"{command_manager.CMD_CREATE_SUBSCRIBER} / {command_manager.CMD_ADD_SUBSCRIBER}",
            "description": "Create a subscriber entry for any destination.",
            "example": example(
                command_manager.CMD_CREATE_SUBSCRIBER,
                Destination="<hex destination>",
                TopicID="<TopicID>",
            ),
        },
        {
            "title": command_manager.CMD_RETRIEVE_SUBSCRIBER,
            "description": "Fetch subscriber metadata by SubscriberID.",
            "example": example(
                command_manager.CMD_RETRIEVE_SUBSCRIBER,
                SubscriberID="<SubscriberID>",
            ),
        },
        {
            "title": f"{command_manager.CMD_DELETE_SUBSCRIBER} / {command_manager.CMD_REMOVE_SUBSCRIBER}",
            "description": "Remove a subscriber mapping.",
            "example": example(
                command_manager.CMD_DELETE_SUBSCRIBER,
                SubscriberID="<SubscriberID>",
            ),
        },
        {
            "title": command_manager.CMD_PATCH_SUBSCRIBER,
            "description": "Update subscriber metadata by SubscriberID.",
            "example": example(
                command_manager.CMD_PATCH_SUBSCRIBER,
                SubscriberID="<SubscriberID>",
                Metadata={"tag": "updated"},
            ),
        },
    ]


def format_topic_entry(index: int, topic: Topic) -> str:
    """Create a single line describing a topic entry."""

    description = f" - {topic.topic_description}" if topic.topic_description else ""
    topic_id = topic.topic_id or "<unassigned>"
    return f"{index}. {topic.topic_name} [{topic.topic_path}] (ID: {topic_id}){description}"


def format_topic_list(topics: List[Topic]) -> List[str]:
    """Create a formatted list of topics suitable for LXMF reply bodies."""

    if not topics:
        return ["No topics registered yet."]
    return [format_topic_entry(idx, topic) for idx, topic in enumerate(topics, start=1)]


def topic_subscribe_hint(subscribe_command: str) -> str:
    """Provide a subscription hint for help replies."""

    example = json.dumps(
        {"Command": subscribe_command, "TopicID": "<TopicID>"},
        sort_keys=True,
    )
    return f"Send the command payload {example} to subscribe to a topic from the list above."


def format_subscriber_entry(index: int, subscriber: Subscriber) -> str:
    """Create a single line describing a subscriber entry."""

    metadata = subscriber.metadata or {}
    metadata_str = json.dumps(metadata, sort_keys=True)
    topic_id = subscriber.topic_id or "<any>"
    subscriber_id = subscriber.subscriber_id or "<pending>"
    return (
        f"{index}. {subscriber.destination} subscribed to {topic_id} "
        f"(SubscriberID: {subscriber_id}) metadata={metadata_str}"
    )


def format_subscriber_list(subscribers: List[Subscriber]) -> List[str]:
    """Create a formatted list of subscribers for LXMF replies."""

    if not subscribers:
        return ["No subscribers registered yet."]
    return [
        format_subscriber_entry(idx, subscriber)
        for idx, subscriber in enumerate(subscribers, start=1)
    ]


def format_attachment_entry(index: int, attachment: FileAttachment) -> str:
    """Create a single line describing a stored file or image."""

    category = attachment.category or "file"
    attachment_id = attachment.file_id if attachment.file_id is not None else "<pending>"
    media_suffix = f" ({attachment.media_type})" if attachment.media_type else ""
    size_text = f", size={attachment.size} bytes" if attachment.size is not None else ""
    return (
        f"{index}. {attachment.name}{media_suffix} "
        f"(ID: {attachment_id}, category={category}{size_text})"
    )


def format_attachment_list(
    attachments: List[FileAttachment], *, empty_text: str
) -> List[str]:
    """Create a formatted list of attachments for LXMF replies."""

    if not attachments:
        return [empty_text]
    return [
        format_attachment_entry(index, attachment)
        for index, attachment in enumerate(attachments, start=1)
    ]
