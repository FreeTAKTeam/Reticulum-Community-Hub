# Reticulum-Telemetry-Hub (RTH)

![image](https://github.com/user-attachments/assets/ba29799c-7194-4052-aedf-1b5e1c8648d5)

Reticulum-Telemetry-Hub (RTH) is an independent component within the [Reticulum](https://reticulum.network/) / [lXMF](https://github.com/markqvist/LXMF) ecosystem, designed to manage a complete TCP node across a Reticulum-based network.
The RTH  enable communication and data sharing between clients like [Sideband](https://github.com/FreeTAKTeam/Sideband](https://github.com/markqvist/Sideband)) or Meshchat, enhancing situational awareness and operational efficiency in distributed networks.

## Core Functionalities

The Reticulum-Telemetry-Hub can perform the following key functions:

- **One to Many & Topic-Targeted Messages**: RTH supports broadcasting messages to all connected clients or filtering the fan-out by topic tags maintained in the hub's subscriber registry.
- By sending a message to the hub, it will be distributed to all clients connected to the network or, when the payload includes a `TopicID`, only to the peers subscribed to that topic. *(Initial implementation - Experimental)*
- **Telemetry Collector**: RTH acts as a telemetry data repository, collecting data from all connected clients.
  Currently, this functionality is focused on Sideband clients that have enabled their Reticulum identity. By  rewriting the code we hope to see a wider implementation of Telemetry in other applications.
- **Replication Node**: RTH uses the LXMF router to ensure message delivery even when the target client is offline. If a message's destination is not available at the time of sending, RTH will save the message and deliver it once the client comes online.
- **Reticulum Transport**: RTH uses Reticulum  as a transport node, routing traffic to other peers, passing network announcements, and fulfilling path requests.

## Installation

To install Reticulum-Telemetry-Hub, clone the repository and proceed with the following steps:

```bash
git clone https://github.com/FreeTAKTeam/Reticulum-Telemetry-Hub.git
cd Reticulum-Telemetry-Hub
```

Create the environment

Choose a directory where you want the Telemetry Hub to live:

```bash
python3 -m venv .venv
```

 Activate it

```bash
source .venv/bin/activate
```

You will now see (.venv) in your shell prompt. you can now

```bash
pip install --upgrade pip
pip install rns lxmf
```

## Configuration

until we implement the wizard you will need to configure different config files.

## RNS Config file

located under ```/[USERNAME]/.reticulum```

minimal configuration

``` ini
[reticulum]  
  enable_transport = True
    share_instance = Yes

[interfaces]
  [[TCP Server Interface]]
  type = TCPServerInterface
  interface_enabled = True

  # This configuration will listen on all IP
  # interfaces on port 4242

  listen_ip = 0.0.0.0
  listen_port = 4242
```

## Router Config File

located under ```/[USERNAME]/.lxmd```

``` ini
[propagation]
enable_node = yes
# Automatic announce interval in minutes, suggested.
announce_interval = 10
propagation_transfer_max_accepted_size = 1024

[lxmf]
display_name = RTH_router

```

## Service

In order to start the router  automatically on startup, we will need to install a /etc/systemd/system/lxmd.service file:

``` ini
[Unit]
Description=Reticulum LXMF Daemon (lxmd)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/lxmd
Restart=on-failure
User=root  # Change this if you run lxmd as a non-root user
WorkingDirectory=/usr/local/bin  # Adjust to where lxmd is located
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

## Usage

Enable and start the service: Once the service file is created, run the following commands to enable and start the service:

```bash
Copy code
sudo systemctl daemon-reload
sudo systemctl enable lxmd.service
sudo systemctl start lxmd.service
```

Ensure your Reticulum network  is operational and configure for the full functionality of RTH.
Once installed and configured, you can start the Reticulum-Telemetry-Hub directly from the package entry point:

```bash
# from the repository root
python -m reticulum_telemetry_hub.reticulum_server \
    --storage_dir ./RTH_Store \
    --display_name "RTH" \
    [--daemon --service gpsd]
```

### Sending commands with parameters

RTH consumes LXMF commands from the `Commands` field (numeric field ID `9`). Each command is a JSON object inside that array and may include either the string key `Command` or the numeric key `0` (`PLUGIN_COMMAND`) for the command name. The server now accepts the following shapes:

- A plain JSON object: `[{"Command": "join"}]`
- A JSON string that parses to an object: `[ "{\"Command\": \"join\"}" ]`
- Sideband-style numeric wrapper that RTH unwraps automatically: `[{"0": "{\"Command\":\"join\"}"}]`

Parameters are provided alongside the command name in the same object. RTH tolerates common casing differences (`TopicID`, `topic_id`, `topic_id`, etc.) and will prompt for anything still missing.

**Typical commands with parameters**

```json
[{"Command": "CreateTopic", "TopicName": "Weather", "TopicPath": "environment/weather"}]
```

```json
[{"Command": "SubscribeTopic", "TopicID": "<TopicID>", "RejectTests": true, "Metadata": {"role": "field-station"}}]
```

```json
[{"Command": "PatchTopic", "TopicID": "<TopicID>", "TopicDescription": "New description"}]
```

You can stack multiple commands by adding more objects to the array. If a required field is missing, the hub will ask for it and keep the partially supplied values. Reply with another command object that includes the missing fields--RTH merges it with your earlier attempt:

1. Send a partial command: `[{"Command": "CreateTopic", "TopicName": "Weather"}]`
2. The hub replies asking for `TopicPath` and shows an example.
3. Reply with the missing field only (or the full payload): `[{"Command": "CreateTopic", "TopicPath": "environment/weather"}]`

The full list of supported command names (with examples) is in `docs/supportedCommands.md`; the in-code reference lives in `reticulum_telemetry_hub/reticulum_server/command_text.py`.

### Topic-targeted broadcasts

RTH keeps a lightweight topic registry via its API, letting operators create topics, add subscribers and limit message delivery to interested peers. Use the `CreateTopic`/`ListTopic` commands to define topic IDs and describe them. Connected clients can then issue the `SubscribeTopic` command so the hub records their LXMF destination hashes under the appropriate topic.

To create a topic, send a `CreateTopic` command payload. For example, Sideband operators commonly issue:

```json
{"Command": "CreateTopic","TopicName": "Weather", "TopicPath": "environment/weather"}
```

This is the exact payload the hub expects (`reticulum_telemetry_hub/reticulum_server/command_manager.py:424-431`), so any LXMF client can reuse it when spawning new operational channels.

RTH  also tolerates Sideband's positional fallback that shows up in logs like `Fields: {9: {0: "CreateTopic", 1: "Weather", 2: "environment/weather"}}`. The hub maps the numeric positions into the expected fields for known commands, so the payload above is treated the same as the JSON example earlier.

Any message sent to the hub that includes a `TopicID` (in the LXMF fields or a command payload) will only be forwarded to the subscribers registered for that topic. The hub automatically refreshes the registry from the API, so new subscriptions take effect without restarting the process.

### Command-line options

| Flag | Description |
| --- | --- |
| `--storage_dir` | Directory that holds LXMF storage and the hub identity (defaults to `./RTH_Store`). |
| `--display_name` | Human-readable label announced with your LXMF destination. |
| `--announce-interval` | Seconds between LXMF identity announcements (defaults to 60). |
| `--hub-telemetry-interval` | Seconds between local telemetry snapshots (defaults to 600 or `$RTH_HUB_TELEMETRY_INTERVAL`). |
| `--service-telemetry-interval` | Seconds between service collector polls (defaults to 900 or `$RTH_SERVICE_TELEMETRY_INTERVAL`). |
| `--embedded` | Run the LXMF daemon in-process. |
| `--daemon` | Enable daemon mode so the hub samples telemetry autonomously. |
| `--service NAME` | Enable optional daemon services such as `gpsd` (repeat the flag for multiple services). |

### Embedded vs. external ``lxmd``

RTH can rely on an external ``lxmd`` process (the default) or it can host the
delivery/propagation threads internally via the ``--embedded``/``--embedded-lxmd``
flag. Choose the mode that best matches your deployment:

* **External daemon (default)** – ideal for production installs that already run
  Reticulum infrastructure. Follow the configuration snippets above to create
  ``~/.reticulum/config`` and ``~/.lxmd/config`` and use your init system (for
  example ``systemd``) to keep ``lxmd`` alive. The hub connects to that router
  and benefits from the daemon’s own storage limits and lifecycle management.
* **Embedded ``lxmd``** – useful for development, CI or constrained hosts where
  running a companion service is impractical. Launch the server with
  ``python -m reticulum_telemetry_hub.reticulum_server --embedded`` (combine it
  with ``--storage_dir`` to point at a temporary workspace). The embedded daemon
  reads the same config files as the external one via the
  ``HubConfigurationManager`` and automatically persists telemetry snapshots
  emitted by the LXMF router. Tweak ``[propagation]`` settings in
  ``~/.lxmd/config`` (announce interval, enable_node, etc.) to control the in
  process behaviour.

### Daemon mode & services

Passing `--daemon` tells the hub to spin up the `TelemetrySampler` along with any
services requested via `--service`. The sampler periodically snapshots the local
`TelemeterManager`, persists the payload and republishes it to every connected
client without manual intervention. Additional services (for example `gpsd`)
run in their own threads and update specialized sensors when the host hardware
is present. Each service self-identifies whether it can start so the daemon can
gracefully run on hardware that lacks certain peripherals.

These background workers honor the normal `shutdown()` lifecycle hooks, making
it safe to run the hub under `systemd`, `supervisord` or similar process
managers. `pytest tests/test_reticulum_server_daemon.py -q` exercises the daemon
mode in CI and verifies that it collects telemetry automatically.

### Project Roadmap

- [x] **Transition to Command-Based Server Joining**: Shift the "joining the server" functionality from an announce-based method to a command-based approach for improved control and scalability.
- [ ] **Configuration Wizard Development**: Introduce a user-friendly wizard to simplify the configuration process.
- [ ] **Integration with TAK_LXMF Bridge**: Incorporate RTH into the TAK_LXMF bridge to strengthen the link between TAK devices and Reticulum networks.
- [ ] **Foundation for FTS "Flock of Parrot"**: Use RTH as the base for implementing the FreeTAKServer "Flock of Parrot" concept, aiming for scalable, interconnected FTS instances.

## Contributing

We welcome and encourage contributions from the community! To contribute, please fork the repository and submit a pull request. Make sure that your contributions adhere to the project's coding standards and include appropriate tests.

## License

This project is licensed under the Creative Commons License Attribution-NonCommercial-ShareAlike 4.0 International. For more details, refer to the `LICENSE` file in the repository.

## Support

For any issues or support, feel free to open an issue on this GitHub repository or join the FreeTAKServer community on [Discord](The FTS Discord Server).

## Support Reticulum

You can help support the continued development of open, free and private communications systems by donating via one of the following channels to the original Reticulm author:

* Monero: 84FpY1QbxHcgdseePYNmhTHcrgMX4nFfBYtz2GKYToqHVVhJp8Eaw1Z1EedRnKD19b3B8NiLCGVxzKV17UMmmeEsCrPyA5w
* Ethereum: 0xFDabC71AC4c0C78C95aDDDe3B4FA19d6273c5E73
* Bitcoin: 35G9uWVzrpJJibzUwpNUQGQNFzLirhrYAH
* Ko-Fi: https://ko-fi.com/markqvist


