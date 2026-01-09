# Supported Commands

Commands are split into **Public** (end users) and **Protected** (admin UI). Every REST endpoint maps to an LXMF command, and all LXMF commands are exposed over REST.

Public commands:

| Command | Description | Example in chat |
| --- | --- | --- |
| `Help` | Returns a Markdown list of available commands (no descriptions). | ``\\\[{"Command":"Help"}]`` |
| `Examples` | Returns a Markdown list with command descriptions and JSON payload examples. | ``\\\[{"Command":"Examples"}]`` |
| `join` | Register your LXMF destination with the hub so you can receive replies. | ``\\\[{"Command":"join"}]`` |
| `leave` | Remove your destination from the hub's connection list. | ``\\\[{"Command":"leave"}]`` |
| `ListTopic` | List every registered topic and its ID. | ``\\\[{"Command":"ListTopic"}]`` |
| `RetrieveTopic` | Fetch a topic by `TopicID`. | ``\\\[{"Command":"RetrieveTopic","TopicID":"<TopicID>"}]`` |
| `SubscribeTopic` | Subscribe the sending destination to a topic. Supports optional `RejectTests` and `Metadata`. | ``\\\[{"Command":"SubscribeTopic","TopicID":"<TopicID>","RejectTests":true,"Metadata":{"role":"field-station"}}]`` |
| `ListFiles` | List file attachments stored by the hub. | ``\\\[{"Command":"ListFiles"}]`` |
| `ListImages` | List image attachments stored by the hub. | ``\\\[{"Command":"ListImages"}]`` |
| `RetrieveFile` | Retrieve a stored file by `FileID`. Response includes `FIELD_FILE_ATTACHMENTS`. | ``[{"Command":"RetrieveFile","FileID":1}]`` |
| `RetrieveImage` | Retrieve a stored image by `FileID`. Response includes `FIELD_IMAGE`. | ``[{"Command":"RetrieveImage","FileID":1}]`` |
| `getAppInfo` | Return the configured app name, version, and description from `config.ini`. | ``\\\[{"Command":"getAppInfo"}]`` |
| `TelemetryRequest` (`1`) | Request telemetry snapshots since a UNIX timestamp. Optional `TopicID` scopes results to a topic. | ``[{"1":1700000000,"TopicID":"<TopicID>"}]`` |

Protected commands:

| Command | Description | Example in chat |
| --- | --- | --- |
| `GetStatus` | Return dashboard metrics and telemetry counts. | ``[{"Command":"GetStatus"}]`` |
| `ListEvents` | Return recent hub events. | ``[{"Command":"ListEvents"}]`` |
| `ListClients` | List the LXMF destinations currently joined to the hub. | ``[{"Command":"ListClients"}]`` |
| `ListIdentities` | List identities with moderation status. | ``[{"Command":"ListIdentities"}]`` |
| `BanIdentity` | Ban an identity. | ``[{"Command":"BanIdentity","Identity":"<hash>"}]`` |
| `UnbanIdentity` | Remove bans/blackholes for an identity. | ``[{"Command":"UnbanIdentity","Identity":"<hash>"}]`` |
| `BlackholeIdentity` | Blackhole an identity. | ``[{"Command":"BlackholeIdentity","Identity":"<hash>"}]`` |
| `CreateTopic` | Create a topic with a name and path. | ``[{"Command":"CreateTopic","TopicName":"Weather","TopicPath":"environment/weather"}]`` |
| `PatchTopic` | Update fields on a topic by `TopicID`. | ``[{"Command":"PatchTopic","TopicID":"<TopicID>","TopicDescription":"New description"}]`` |
| `DeleteTopic` | Delete a topic (and unsubscribe listeners). | ``[{"Command":"DeleteTopic","TopicID":"<TopicID>"}]`` |
| `AssociateTopicID` | Associate uploaded attachments with a `TopicID`. | ``[{"Command":"AssociateTopicID","TopicID":"<TopicID>"}]`` |
| `ListSubscriber` | List every subscriber registered with the hub. | ``[{"Command":"ListSubscriber"}]`` |
| `CreateSubscriber` / `AddSubscriber` | Create a subscriber entry for any destination. | ``[{"Command":"CreateSubscriber","Destination":"<hex destination>","TopicID":"<TopicID>"}]`` |
| `RetrieveSubscriber` | Fetch subscriber metadata by `SubscriberID`. | ``[{"Command":"RetrieveSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `DeleteSubscriber` / `RemoveSubscriber` | Remove a subscriber mapping. | ``[{"Command":"DeleteSubscriber","SubscriberID":"<SubscriberID>"}]`` |
| `PatchSubscriber` | Update subscriber metadata by `SubscriberID`. | ``[{"Command":"PatchSubscriber","SubscriberID":"<SubscriberID>","Metadata":{"tag":"updated"}}]`` |
| `GetConfig` | Return the raw `config.ini` content. | ``[{"Command":"GetConfig"}]`` |
| `ValidateConfig` | Validate a new config.ini payload without applying. | ``[{"Command":"ValidateConfig","ConfigText":"<ini content>"}]`` |
| `ApplyConfig` | Apply a new config.ini payload. | ``[{"Command":"ApplyConfig","ConfigText":"<ini content>"}]`` |
| `RollbackConfig` | Roll back config.ini using the latest backup. | ``[{"Command":"RollbackConfig"}]`` |
| `FlushTelemetry` | Delete stored telemetry snapshots. | ``[{"Command":"FlushTelemetry"}]`` |
| `ReloadConfig` | Reload config.ini from disk. | ``[{"Command":"ReloadConfig"}]`` |
| `DumpRouting` | Return connected destination hashes. | ``[{"Command":"DumpRouting"}]`` |

Notes:

- For clients that do not support `Commands` (e.g. Meshchat), prefix the message body with ``\\\`` so the hub treats it as a command payload (e.g., ``\\\join`` or ``\\\{"Command":"SubscribeTopic","TopicID":"<TopicID>"}``).
- RTH accepts common field name variants (e.g., `TopicID`, `topicId`, `topic_id`, `TopicPath`, `topic_path`).
- If required fields are missing, RTH replies with the missing keys and merges your follow-up payload with the original so you can send only the missing fields.
