#!/usr/bin/env python3
"""
Example: connect to FreeTAKServer via plain TCP and send XML CoT events.

This script connects to an FTS instance over a clear TCP socket (port 8087 by
default【700031643051780†L165-L168】) and sends a specific Cursor‑on‑Target (CoT) event in
UTF‑8 XML form (TAK protocol version 0【245157843335854†L72-L75】).  A random delay between
transmissions honours FTS’s anti‑DoS throttle【245157843335854†L99-L113】.  After each send,
the script prints a timestamp and whether the socket is still open to provide
status feedback.

Adjust `FTS_HOST`, `FTS_PORT`, and the XML payload to suit your environment.

Requires: `pytak` (for compatibility with the TAK ecosystem) installed via
`pip install pytak`.
"""

import asyncio
import random
import time

import pytak  # PyTAK installed for TAK/CoT compatibility

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Hostname or IP of your FreeTAKServer
FTS_HOST = "137.184.101.250"
# Default clear‑text CoT port for FTS【700031643051780†L165-L168】
FTS_PORT = 8087
# Delay range between messages (seconds) to respect FTS throttle【245157843335854†L99-L113】
MIN_SLEEP = 1.0
MAX_SLEEP = 3.0

# Custom CoT event to send (TAK protocol v0).  Replace values as needed.
COT_XML = """<?xml version="1.0"?>
<event version="2.0"
       uid="S-1-5-21-249124979-4228309938-1977687263-1004"
       type="a-f-G-U-h"
       how="m-g"
       start="2022-11-28T19:33:03.46Z"
       time="2022-11-28T19:33:03.46Z"
       stale="2022-11-28T19:39:18.46Z">
    <point le="9999999"
           ce="114.0"
           hae="9999999"
           lon="-115.1180345"
           lat="36.083744"/>
</event>
<detail>
    <__group name="Green"
             role="Team Lead"/>
    <status battery="100"/>
    <takv version="0.2"
          platform="Garmin"
          device="Fenix Pro"
          os=""/>
    <track course="0.00000000"
           speed="0.00000000"/>
    <contact callsign="Charlie-9 Mobile"
             endpoint="*:-1:stcp"/>
    <uid Droid="Charlie-9 Mobile"/>
    <precisionlocation/>
</detail>"""

async def send_event_loop(host: str, port: int) -> None:
    """Continuously connect to the FTS server and send the custom XML event."""
    while True:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            print(f"Connected to FTS at {host}:{port}")
            # pre‑encode XML for efficiency
            cot_bytes = COT_XML.encode('utf-8')
            while True:
                writer.write(cot_bytes)
                await writer.drain()
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(f"{timestamp} – sent custom CoT; socket open: {not writer.is_closing()}")
                await asyncio.sleep(random.uniform(MIN_SLEEP, MAX_SLEEP))
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionRefusedError) as exc:
            print(f"Connection error: {exc} – retrying in 5 s…")
            await asyncio.sleep(5)
        except Exception as exc:
            print(f"Unexpected error: {exc} – retrying in 5 s…")
            await asyncio.sleep(5)

async def main() -> None:
    await send_event_loop(FTS_HOST, FTS_PORT)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exited by user")
