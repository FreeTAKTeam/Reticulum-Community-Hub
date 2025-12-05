#!/usr/bin/env python3
"""
Example script for connecting to a TAK/FreeTAKServer (FTS) using plain TCP
and XML CoT (protocol version 0) with PyTAK.

This script demonstrates how to create a stable connection to a FreeTAKServer
(FTS) instance, send periodic "Hello" CoT events (also known as
``takPing`` events) over a clear TCP connection, and provide simple status
output indicating that the socket is functioning.  The script uses
``asyncio`` for non‑blocking network I/O and ``pytak`` for generating CoT
messages.  By default, PyTAK sends and receives "TAK Protocol Payload –
Version 0" (UTF‑8 XML) messages【245157843335854†L72-L75】, which is the plain‑text XML
format used by TAK/FTS servers.

Before running this example, make sure PyTAK is installed (``pip install
pytak``) and adjust ``FTS_HOST`` and ``FTS_PORT`` to match your server.
The default FTS CoT port for unencrypted (clear) TCP is 8087【700031643051780†L165-L168】.

The script uses a small random delay between sends to respect the FTS
anti–Denial‑of‑Service (DoS) throttle.  FTS limits how frequently a client
can send CoT events.  PyTAK's documentation recommends enabling
``FTS_COMPAT`` or configuring a sleep period【245157843335854†L99-L113】; here we
implement a similar delay manually.
"""

import asyncio
import random
import time

import pytak  # PyTAK is used only to generate CoT events

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Replace with the hostname or IP address of your FreeTAKServer instance.
FTS_HOST = "137.184.101.250"
# The clear‑text CoT service port; the default for FTS is 8087
FTS_PORT = 8087

# Delay range (in seconds) between CoT transmissions.  FTS enforces rate
# limits; using a random back‑off helps avoid tripping the anti‑DoS logicmodify the scr
MIN_SLEEP = 1.0
MAX_SLEEP = 3.0


async def send_hello_loop(host: str, port: int) -> None:
    """Continuously connect to the server and send Hello events.

    On connection errors the loop waits five seconds and attempts to
    reconnect.  Each successful send prints a status line indicating that
    the connection is alive and the data was transmitted.
    """
    while True:
        try:
            # Open a TCP connection to the FTS CoT service.
            reader, writer = await asyncio.open_connection(host, port)
            print(f"Connected to FTS at {host}:{port}")

            # Loop sending Hello events until an exception occurs.
            while True:
                # Generate a basic "Hello" CoT event (uid defaults to 'takPing').
                # PyTAK returns a bytes object containing XML【245157843335854†L72-L75】.
                cot_bytes = pytak.hello_event()

                # Write the event to the TCP stream.  Since CoT events are
                # terminated by the closing '</event>' tag, we don't need an
                # additional delimiter.
                writer.write(cot_bytes)
                await writer.drain()

                # Status output: check whether the writer is still open.
                # ``is_closing()`` returns True if the transport is shutting down.
                sock_ok = not writer.is_closing()
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(f"{timestamp} – sent Hello (takPing); socket open: {sock_ok}")

                # Sleep for a random interval to respect FTS rate limiting【245157843335854†L99-L113】.
                delay = random.uniform(MIN_SLEEP, MAX_SLEEP)
                await asyncio.sleep(delay)

        except (
            asyncio.IncompleteReadError,
            ConnectionResetError,
            ConnectionRefusedError,
        ) as exc:
            # Connection lost or refused; report the error and retry after a pause.
            print(f"Connection error: {exc} – reconnecting in 5 seconds…")
            await asyncio.sleep(5)
        except Exception as exc:
            # Catch‑all for unexpected errors; log and break to retry.
            print(f"Unexpected error: {exc} – reconnecting in 5 seconds…")
            await asyncio.sleep(5)


async def main() -> None:
    """Entry point for the asyncio event loop."""
    await send_hello_loop(FTS_HOST, FTS_PORT)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exited by user")
