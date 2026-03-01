# Remote Access

This guide explains how to reach a Reticulum Community Hub (RCH) instance from another machine.

## Important Notes

- `rch start` is intended for local desktop use and binds the API to `127.0.0.1`.
- For LAN or WAN access, run the gateway directly with `--api-host 0.0.0.0` (or another reachable interface).
- For a single-command launcher that installs the backend from local source into a venv and starts both services, run `./run_server_ui_remote.sh`.
- `run_server_ui_remote.sh` is useful for manual remote testing; for a persistent Linux deployment, prefer a `systemd` service for the backend.
- `run_server_ui_remote.sh` only preconfigures the REST base URL by default; the UI derives the WebSocket URL from that value unless you explicitly set `VITE_RTH_WS_BASE_URL`.
- On first remote load, the UI should open the Connect page so you can enter the API key and log in before the live WebSocket streams start.
- Remote clients must authenticate with `RTH_API_KEY`.
- Remote requests can use either `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- If the hub is reachable over the public internet, prefer a VPN or HTTPS/WSS behind a reverse proxy.

## Common Host Setup

Set an API key on the machine running RCH before you start the gateway:

```bash
# Linux/macOS
export RTH_API_KEY="change-this"

# Windows PowerShell
$env:RTH_API_KEY = "change-this"
```

`RCH_API_KEY` is still accepted as a legacy alias, but `RTH_API_KEY` is the preferred name.

Start the gateway on a reachable interface:

```bash
python -m reticulum_telemetry_hub.northbound.gateway --data-dir ./RCH_Store --api-host 0.0.0.0 --port 8000
```

Then:

1. Allow inbound TCP traffic on port `8000` in the host firewall.
2. If the host is behind a router, forward external port `8000` to the RCH machine.
3. If the host is in a cloud environment, allow port `8000` in the provider security group or firewall policy.

## Persisting the API Key Locally

If you only set `RTH_API_KEY` with `export`, it lasts only for the current shell session. For a persistent setup on Linux, use one of these patterns:

### Option A: Persist for Manual Shell Launches

Add the export to the account that starts RCH:

```bash
echo 'export RTH_API_KEY="change-this"' >> ~/.profile
```

Then reload the shell environment:

```bash
source ~/.profile
```

Use this when you start the gateway manually from a terminal.

### Option B: Persist for a Service

Store the key in a dedicated environment file owned by root:

```bash
sudo install -d -m 0755 /etc/rch
sudo sh -c 'printf "RTH_API_KEY=change-this\n" > /etc/rch/rch.env'
sudo chmod 600 /etc/rch/rch.env
```

Use this when RCH runs under `systemd`. The service file can then load the key automatically with `EnvironmentFile=/etc/rch/rch.env`.

## 1. Raspberry Pi on the Same LAN

This is the simplest case: RCH runs on a Raspberry Pi and the user connects from another computer on the same local network.

### On the Raspberry Pi

1. Start the gateway with `--api-host 0.0.0.0`.
2. Find the Pi's LAN address (for example `192.168.1.50`).
3. Make sure port `8000` is allowed locally.

### On the Client Computer

Use the Pi's LAN IP:

- REST base URL: `http://192.168.1.50:8000`
- WebSocket base URL: `ws://192.168.1.50:8000`

If you are using the RCH web UI, open the Connect page and enter:

- `Base URL`: `http://192.168.1.50:8000`
- `WebSocket Base URL`: `ws://192.168.1.50:8000`
- `API Key` or `Bearer Token`: the same value as `RTH_API_KEY`

If you are calling the API directly, include one of these headers:

```text
X-API-Key: change-this
Authorization: Bearer change-this
```

### LAN Troubleshooting

- If the client cannot connect, confirm both devices are on the same subnet.
- Verify the Pi firewall is not blocking port `8000`.
- Make sure you are using the Pi's LAN address, not `127.0.0.1`.

## 2. Remote Server with a Public IP

Use this when RCH runs on a server that is reachable from a completely different network.

### On the Server

1. Start the gateway with `--api-host 0.0.0.0`.
2. Confirm the server has a public IP or a DNS name that resolves to it.
3. Open port `8000` in the server firewall and any cloud network firewall.
4. Keep `RTH_API_KEY` set before starting the process.

### On the Client Computer

Use the server's public address:

- REST base URL: `http://203.0.113.10:8000`
- WebSocket base URL: `ws://203.0.113.10:8000`

If you use a domain name and TLS termination, use:

- REST base URL: `https://rch.example.com`
- WebSocket base URL: `wss://rch.example.com`

Then authenticate with the same API key or bearer token configured on the server.

### Internet Exposure Recommendations

- Prefer `https://` and `wss://` when traffic leaves your local network.
- Restrict inbound access to trusted IP ranges when possible.
- Consider placing RCH behind WireGuard, Tailscale, Caddy, or Nginx instead of exposing raw HTTP.
- Do not expose RCH publicly without `RTH_API_KEY`.

### WAN Troubleshooting

- If the host is behind NAT, confirm the router forwards the correct port.
- If the server is in the cloud, verify the public firewall permits inbound TCP on `8000`.
- If REST works but live updates do not, confirm WebSocket traffic is also allowed and proxied.

## 3. Linux Service Setup (`systemd`)

Use this when you want the gateway to start automatically on boot and keep running in the background.

### Example Layout

- Source checkout: `/opt/Reticulum-Telemetry-Hub`
- Virtual environment: `/opt/Reticulum-Telemetry-Hub/venv_linux`
- Data directory: `/var/lib/rch`
- API key file: `/etc/rch/rch.env`

### Example Service Unit

Create `/etc/systemd/system/rch-gateway.service`:

```ini
[Unit]
Description=Reticulum Community Hub Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rch
Group=rch
WorkingDirectory=/opt/Reticulum-Telemetry-Hub
EnvironmentFile=/etc/rch/rch.env
ExecStart=/opt/Reticulum-Telemetry-Hub/venv_linux/bin/python -m reticulum_telemetry_hub.northbound.gateway --data-dir /var/lib/rch --api-host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Exact Install Commands

If you want a copy-pasteable setup on Linux, the block below creates the `rch` service account, creates the data and environment directories, writes the service unit, and enables the service:

```bash
sudo useradd --system --create-home --home-dir /var/lib/rch --shell /usr/sbin/nologin rch
sudo install -d -o rch -g rch -m 0755 /var/lib/rch
sudo install -d -m 0755 /etc/rch
sudo sh -c 'printf "RTH_API_KEY=change-this\n" > /etc/rch/rch.env'
sudo chmod 600 /etc/rch/rch.env

sudo tee /etc/systemd/system/rch-gateway.service > /dev/null <<'EOF'
[Unit]
Description=Reticulum Community Hub Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rch
Group=rch
WorkingDirectory=/opt/Reticulum-Telemetry-Hub
EnvironmentFile=/etc/rch/rch.env
ExecStart=/opt/Reticulum-Telemetry-Hub/venv_linux/bin/python -m reticulum_telemetry_hub.northbound.gateway --data-dir /var/lib/rch --api-host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rch-gateway
sudo systemctl start rch-gateway
sudo systemctl status rch-gateway
```

Adjust the `WorkingDirectory` and `ExecStart` paths if your source checkout or virtual environment lives somewhere else.

### Enable and Start the Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable rch-gateway
sudo systemctl start rch-gateway
sudo systemctl status rch-gateway
```

### Update the API Key Later

If you change the key in `/etc/rch/rch.env`, restart the service so the new value is loaded:

```bash
sudo systemctl restart rch-gateway
```

### Linux Service Notes

- Keep `/etc/rch/rch.env` readable only by privileged users.
- Use a dedicated service account such as `rch` instead of `root`.
- If you also need remote UI access, serve the built UI behind Nginx/Caddy or run the UI separately; the `systemd` example above manages the backend gateway.

## Summary

- Same LAN: connect to the hub's private IP, such as `192.168.x.x`.
- Different network: connect to the hub's public IP or DNS name.
- In both cases, run the gateway on a reachable interface and authenticate remote requests.
- For Linux servers, persist `RTH_API_KEY` in an environment file and run the gateway under `systemd` for automatic startup.
