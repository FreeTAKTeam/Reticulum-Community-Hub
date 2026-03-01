# Remote Access

This guide explains how to reach a Reticulum Community Hub (RCH) instance from another machine.

## Important Notes

- `rch start` is intended for local desktop use and binds the API to `127.0.0.1`.
- For LAN or WAN access, run the gateway directly with `--api-host 0.0.0.0` (or another reachable interface).
- For a single-command launcher that installs the latest backend package into a venv and starts both services, run `./run_server_ui_remote.sh`.
- Remote clients must authenticate with `RTH_API_KEY`.
- Remote requests can use either `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- If the hub is reachable over the public internet, prefer a VPN or HTTPS/WSS behind a reverse proxy.

## Common Host Setup

Set an API key on the machine running RCH:

```bash
# Linux/macOS
export RTH_API_KEY="change-this"

# Windows PowerShell
$env:RTH_API_KEY = "change-this"
```

Start the gateway on a reachable interface:

```bash
python -m reticulum_telemetry_hub.northbound.gateway --data-dir ./RCH_Store --api-host 0.0.0.0 --port 8000
```

Then:

1. Allow inbound TCP traffic on port `8000` in the host firewall.
2. If the host is behind a router, forward external port `8000` to the RCH machine.
3. If the host is in a cloud environment, allow port `8000` in the provider security group or firewall policy.

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

## Summary

- Same LAN: connect to the hub's private IP, such as `192.168.x.x`.
- Different network: connect to the hub's public IP or DNS name.
- In both cases, run the gateway on a reachable interface and authenticate remote requests.
