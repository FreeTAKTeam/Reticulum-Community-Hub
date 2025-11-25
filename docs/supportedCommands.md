# Supported Commands

Place commands in the LXMF `Commands` field (field ID `9`) as a JSON array of objects. Each object may use either the string key `Command` or the numeric key `0` (`PLUGIN_COMMAND`) for the command name. Telemetry requests use numeric key `1` (`TelemetryController.TELEMETRY_REQUEST`).

| Command | Description | Example |
| --- | --- | --- |
| `Help` | Returns a short help message with the available commands and examples. | ``[{"Command":"Help"}]`` |
| `join` | Register your LXMF destination with the hub so you can receive replies. | ``[{"Command":"join"}]`` |
| `leave` | Remove your destination from the hub's connection list. | ``[{"Command":"leave"}]`` |
| `ListClients` | List the LXMF destinations currently joined to the hub. | ``[{"Command":"ListClients"}]`` |
| `getAppInfo` | Return the hub name so you can confirm connectivity. | ``[{"Command":"getAppInfo"}]`` |
| `ListTopic` | List every registered topic and its ID. | ``[{"Command":"ListTopic"}]`` |
| `CreateTopic` | Create a topic with a name and path. | ``[{"Command":"CreateTopic","TopicName":"Weather","TopicPath":"environment/weather"}]`` |
| `RetreiveTopic` | Fetch a topic by `TopicID`. | ``[{"Command":"RetreiveTopic","TopicID":"<TopicID>"}]`` |
| `DeleteTopic` | Delete a topic (and unsubscribe its listeners). | ``[{"Command":"DeleteTopic","TopicID":"<TopicID>"}]`` |
| `PatchTopic` | Update fields on a topic by `TopicID`. | ``[{"Command":"PatchTopic","TopicID":"<TopicID>","TopicDescription":"New description"}]`` |
| `SubscribeTopic` | Subscribe the sending destination to a topic. Supports optional `RejectTests` and `Metadata`. | ``[{"Command":"SubscribeTopic","TopicID":"<TopicID>","RejectTests":true,"Metadata":{"role":"field-station"}}]`` |
| `ListSubscriber` | List every subscriber registered with the hub. | ``[{"Command":"ListSubscriber"}]`` |
| `CreateSubscriber` / `AddSubscriber` | Create a subscriber entry for any destination. | ``[{"Command":"CreateSubscriber","Destination":"<hex destination>","TopicID":"<TopicID>","Metadata":{"tag":"sensor"}}]`` |
| `RetreiveSubscriber` | Fetch subscriber metadata by `SubscriberID`. | ``[{"Command":"RetreiveSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `DeleteSubscriber` / `RemoveSubscriber` | Remove a subscriber mapping. | ``[{"Command":"DeleteSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `PatchSubscriber` | Update subscriber metadata by `SubscriberID`. | ``[{"Command":"PatchSubscriber","SubscriberID":"<SubscriberID>","Metadata":{"tag":"updated"}}]`` |
| `TelemetryRequest` (`1`) | Request telemetry snapshots from all peers since the provided UNIX timestamp. Response includes packed telemetry in `FIELD_TELEMETRY_STREAM` plus a JSON body with human-readable telemetry. | ``[{"1":1700000000}]`` |

Notes:
- RTH accepts common field name variants (e.g., `TopicID`, `topic_id`, `topic_id`, `TopicPath`, `topic_path`).
- If required fields are missing, the hub replies with the missing keys and merges your follow-up payload with the original.
- When the `Commands` field is unavailable, prefix the message body with ``\\\`` so the hub treats it as a command payload (e.g., ``\\\join`` or ``\\\{"Command":"SubscribeTopic","TopicID":"<TopicID>"}``).
- Telemetry responses now mirror the packed stream and also embed a human-readable JSON payload; see `docs/example_telemetry.json` for a sample body.
