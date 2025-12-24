# Reticulum Telemetry Hub (RTH) User Manual

This manual is written for non-technical users. It explains what RTH does,
how to use it, and what to expect with different LXMF clients.

## What is RTH?
RTH is a hub that connects LXMF messaging clients. It helps move messages
between people, keeps simple topic groups, and can share location and other
telemetry when supported by your client and services.

You can think of RTH as a relay station:

- It receives messages and forwards them to the right people.
- It stores recent telemetry (position) so it can be shared on request.
- It can forward location updates into the TAK Tactical network when that service is enabled.

## Which LXMF client are you using?

Different clients have different capabilities when talking to RTH.

### Sideband

Full support:
- Group chat
- Commands
- Telemetry
- TAK integration: chat, position

### MeshChat

Supported:
- Group chat
- TAK integration: chat

Not supported:
- Telemetry

### Columba

Supported:
- Group chat
- TAK integration: chat

Not supported:
- Telemetry

## Common tasks

### Join RTH

1. Open your LXMF client.
2. Add (or select from announces)  the RTH identity.
3. start a chat
4. Use the client’s command or "\\\join"  to chat with the group.

If you are not sure which command to use, type \\\help.

### Send a group message

1. Select the topic or group in your client.
2. Write your message.
3. Send regularly

RTH will deliver the message only to other users who are subscribed to that topic.

### Telemetry (Sideband only)

If you use Sideband and telemetry is enabled:

- select  RTH as the telmetry Hub
- RTH can collect your telemetry data (for example, location).
- RTH can share recent telemetry when requested.

Telemetry will not work in MeshChat or Columba (as Dec 2025).

### TAK integration (optional)

If the TAK service is enabled by your administrator:

- Location updates can be forwarded to a TAK server.
- Chat messages can be mirrored into TAK chat.

If you are unsure whether TAK is enabled, ask your administrator.

## Troubleshooting

### I cannot see the hub or other users

- Make sure you are connected to the correct RTH identity.
- Check that your client is subscribed to the correct topic.
- Ask your administrator to confirm the hub is running.

### Commands do not work

- Confirm you are connected to RTH.
- Ensure you are using a supported command format for your client.

### Telemetry is missing

- Telemetry is only supported in Sideband.
- Make sure telemetry is enabled in your Sideband settings.
- insert RTH idntity as a collector
- Ask your administrator if telemetry collection is enabled on RTH.

## Getting help

If you need help:

- create an issue on github : https://github.com/FreeTAKTeam/Reticulum-Telemetry-Hub 
- Provide your client name (Sideband, MeshChat, or Columba).
- Share the time and a short description of the issue.
