"""Tests for northbound serializers."""

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.northbound.models import SubscriberPayload
from reticulum_telemetry_hub.northbound.models import TopicPayload
from reticulum_telemetry_hub.northbound.serializers import build_subscriber
from reticulum_telemetry_hub.northbound.serializers import build_topic
from reticulum_telemetry_hub.northbound.serializers import serialize_subscriber
from reticulum_telemetry_hub.northbound.serializers import serialize_topic


def test_serialize_topic_round_trip() -> None:
    """Ensure topics serialize to the expected payload."""

    topic = Topic(topic_name="Name", topic_path="/path", topic_description="desc")
    payload = serialize_topic(topic)

    assert payload["TopicName"] == "Name"
    assert payload["TopicPath"] == "/path"


def test_build_topic_from_payload() -> None:
    """Ensure topics build from payloads."""

    payload = TopicPayload(TopicName="Name", TopicPath="/path", TopicDescription="desc")
    topic = build_topic(payload)

    assert topic.topic_name == "Name"
    assert topic.topic_path == "/path"
    assert topic.topic_description == "desc"


def test_build_subscriber_from_payload() -> None:
    """Ensure subscribers build from payloads."""

    payload = SubscriberPayload(Destination="dest", TopicID="topic")
    subscriber = build_subscriber(payload)

    assert subscriber.destination == "dest"
    assert subscriber.topic_id == "topic"


def test_serialize_subscriber_payload() -> None:
    """Ensure subscribers serialize to the expected payload."""

    subscriber = Subscriber(destination="dest", topic_id="topic", metadata={"k": "v"})
    payload = serialize_subscriber(subscriber)

    assert payload["Destination"] == "dest"
    assert payload["TopicID"] == "topic"
