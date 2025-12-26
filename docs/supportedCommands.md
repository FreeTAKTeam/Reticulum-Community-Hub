# Supported Commands

- in clients that do not support  `Commands` (e.g. Meshchat), prefix the message body with ``\\\`` so the hub treats it as a command payload (e.g., ``\\\join`` or ``\\\{"Command":"SubscribeTopic","TopicID":"<TopicID>"}``).
- RTH accepts common field name variants (e.g., `TopicID`, `topicId`, `topic_id`, `TopicPath`, `topic_path`).
- If required fields are missing, RTH  replies with the missing keys and merges your follow-up payload with the original so you can send only the missing fields.


the following commands are supported by RTH


| Command | Description | Example in chat|
| --- | --- | --- |
| `Help` | Returns a short help message with the available commands and examples. | ``\\\[{"Command":"Help"}]`` |
| `join` | Register your LXMF destination with the hub so you can receive replies. | ``\\\[{"Command":"join"}]`` |
| `leave` | Remove your destination from the hub's connection list. | ``\\\[{"Command":"leave"}]`` |
| `ListClients` | List the LXMF destinations currently joined to the hub. | ``\\\[{"Command":"ListClients"}]`` |
| `getAppInfo` | Return the configured app name, version, and description from `config.ini`. | ``\\\[{"Command":"getAppInfo"}]`` |
| `ListTopic` | List every registered topic and its ID. | ``\\\[{"Command":"ListTopic"}]`` |
| `CreateTopic` | Create a topic with a name and path. | ``\\\[{"Command":"CreateTopic","TopicName":"Weather","TopicPath":"environment/weather"}]`` |
| `RetrieveTopic` | Fetch a topic by `TopicID`. | ``\\\[{"Command":"RetrieveTopic","TopicID":"<TopicID>"}]`` |
| `DeleteTopic` | Delete a topic (and unsubscribe its listeners). | ``[{"Command":"DeleteTopic","TopicID":"<TopicID>"}]`` |
| `PatchTopic` | Update fields on a topic by `TopicID`. | ``[{"Command":"PatchTopic","TopicID":"<TopicID>","TopicDescription":"New description"}]`` |
| `SubscribeTopic` | Subscribe the sending destination to a topic. Supports optional `RejectTests` and `Metadata`. | ``\\\[{"Command":"SubscribeTopic","TopicID":"<TopicID>","RejectTests":true,"Metadata":{"role":"field-station"}}]`` |
| `ListSubscriber` | List every subscriber registered with the hub. | ``[{"Command":"ListSubscriber"}]`` |
| `CreateSubscriber` / `AddSubscriber` | Create a subscriber entry for any destination. | ``[{"Command":"CreateSubscriber","Destination":"<hex destination>","TopicID":"<TopicID>","Metadata":{"tag":"sensor"}}]`` |
| `RetrieveSubscriber` | Fetch subscriber metadata by `SubscriberID`. | ``[{"Command":"RetrieveSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `DeleteSubscriber` / `RemoveSubscriber` | Remove a subscriber mapping. | ``[{"Command":"DeleteSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `PatchSubscriber` | Update subscriber metadata by `SubscriberID`. | ``[{"Command":"PatchSubscriber","SubscriberID":"<SubscriberID>","Metadata":{"tag":"updated"}}]`` |
| `TelemetryRequest` (`1`) | Request telemetry snapshots from all peers since the provided UNIX timestamp. Response includes packed telemetry in `FIELD_TELEMETRY_STREAM` plus a JSON body with human-readable telemetry. | ``[{"1":1700000000}]`` |

Notes:
- Telemetry responses now mirror the packed stream and also embed a human-readable JSON payload; see `docs/example_telemetry.json` for a sample body.
- Command casing is permissive (`CreateTopic`, `createtopic`, and `createTopic` are all accepted), but the JSON keys shown above are the clearest to read.

### Tips for building command payloads

- Wrap multiple actions in a single array to reduce round-trips, for example:

  ```json
  [
    {"Command": "join"},
    {"Command": "SubscribeTopic", "TopicID": "<TopicID>"}
  ]
  ```

- Subscriber metadata is merged when you patch or resubmit a command. You can safely send partial structures such as `{"Metadata":{"role":"sensor"}}` without losing existing attributes.
