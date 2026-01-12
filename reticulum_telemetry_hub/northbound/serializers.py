"""Serialization helpers for the northbound API."""

from __future__ import annotations

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic

from .models import SubscriberPayload
from .models import TopicPayload


def serialize_topic(topic: Topic) -> dict:
    """Serialize a topic for JSON output.

    Args:
        topic (Topic): Topic instance.

    Returns:
        dict: Serialized topic payload.
    """

    return topic.to_dict()


def serialize_subscriber(subscriber: Subscriber) -> dict:
    """Serialize a subscriber for JSON output.

    Args:
        subscriber (Subscriber): Subscriber instance.

    Returns:
        dict: Serialized subscriber payload.
    """

    return subscriber.to_dict()


def build_topic(payload: TopicPayload) -> Topic:
    """Build a topic model from a payload.

    Args:
        payload (TopicPayload): Topic payload.

    Returns:
        Topic: Topic instance.
    """

    return Topic(
        topic_id=payload.topic_id,
        topic_name=payload.topic_name or "",
        topic_path=payload.topic_path or "",
        topic_description=payload.topic_description or "",
    )


def build_subscriber(payload: SubscriberPayload) -> Subscriber:
    """Build a subscriber model from a payload.

    Args:
        payload (SubscriberPayload): Subscriber payload.

    Returns:
        Subscriber: Subscriber instance.
    """

    return Subscriber(
        subscriber_id=payload.subscriber_id,
        destination=payload.destination or "",
        topic_id=payload.topic_id,
        reject_tests=payload.reject_tests,
        metadata=payload.metadata or {},
    )
