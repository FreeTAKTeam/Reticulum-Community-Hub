#!/usr/bin/env python3

import asyncio
import xml.etree.ElementTree as ET
from configparser import ConfigParser

import pytak


def make_cot():
    """Generate a custom CoT as XML bytes."""

    # Root event
    root = ET.Element("event")
    root.set("version", "2.0")
    root.set("uid", "S-1-5-21-249124979-4228309938-1977687263-1004")
    root.set("type", "a-f-G-U-h")
    root.set("how", "m-g")
    # fresh times
    root.set("time", pytak.cot_time())
    root.set("start", pytak.cot_time())
    root.set("stale", pytak.cot_time(360))  # 6 minutes from now, adjust as needed

    # Point
    ET.SubElement(
        root,
        "point",
        attrib={
            "lat": "36.083744",
            "lon": "-115.1180345",
            "hae": "9999999",
            "ce": "114.0",
            "le": "9999999",
        },
    )

    # Detail block (nested inside <event>, not separate)
    detail = ET.SubElement(root, "detail")

    ET.SubElement(detail, "__group", attrib={"name": "Green", "role": "Team Lead"})
    ET.SubElement(detail, "status", attrib={"battery": "100"})
    ET.SubElement(
        detail,
        "takv",
        attrib={
            "version": "0.2",
            "platform": "Garmin",
            "device": "Fenix Pro",
            "os": "",
        },
    )
    ET.SubElement(detail, "track", attrib={"course": "0.0", "speed": "0.0"})
    ET.SubElement(
        detail,
        "contact",
        attrib={"callsign": "Charlie-9 Mobile", "endpoint": "*:-1:stcp"},
    )
    ET.SubElement(detail, "uid", attrib={"Droid": "Charlie-9 Mobile"})
    ET.SubElement(detail, "precisionlocation")

    return ET.tostring(root)


class MySender(pytak.QueueWorker):
    """
    Generates CoT and pushes it to the TX queue handled by PyTAK.
    """

    async def handle_data(self, data: bytes):
        await self.put_queue(data)

    async def run(self):
        while True:
            event = make_cot()
            self._logger.info("Sending:\n%s\n", event.decode())
            await self.handle_data(event)
            await asyncio.sleep(5)  # send every 5 seconds


async def main():
    # Configure COT_URL and FTS_COMPAT
    config = ConfigParser()
    config["mycottool"] = {
        # FTS clear CoT port is 8087 by default
        "COT_URL": "tcp://137.184.101.250:8087",
        # avoid FTS DoS protections by inserting random delay
        "FTS_COMPAT": "1",
        # keep TAK_PROTO=0 (XML) – default, but explicit is fine too
        "TAK_PROTO": "0",
        # optional: enable debug logging
        # "DEBUG": "1",
    }
    section = config["mycottool"]

    # Initialize CLITool (creates RX/TX workers based on COT_URL)
    clitool = pytak.CLITool(section)
    await clitool.setup()

    # Register our sender
    clitool.add_tasks({MySender(clitool.tx_queue, section)})

    # Start everything
    await clitool.run()


if __name__ == "__main__":
    asyncio.run(main())
