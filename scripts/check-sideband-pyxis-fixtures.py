#!/usr/bin/env python3
"""Execute pinned Sideband methods and Pyxis codec against synthetic byte vectors.

Usage: python check-sideband-pyxis-fixtures.py ORACLE_DIRECTORY
The directory contains sense.py from Sideband 2000d81a and
LocationTelemetryCodec.{h,cpp} from Pyxis 5181fdd7. Requires RNS and g++.
Only the original Sideband pack/unpack methods execute; platform sensor setup
is replaced by synthetic readings. This does not test phones or radios.
"""
import ast
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from RNS.vendor import umsgpack

HASHES = {
    "sense.py": "a1bcc2aee3234eae6e93a693ded9590e0edbc11350787f692fd7d3e2dfa76470",
    "LocationTelemetryCodec.cpp": "b4349aa44624f337ab73ecc9fd745dcf442a3d5d07621eef65c6d6d7cf4bfc0c",
    "LocationTelemetryCodec.h": "3c0852dbaa04e8df64ba89aea07674453ab8cd21e1dc7b931e17b7d8b117292a",
}


def main():
    oracle = Path(sys.argv[1]).resolve()
    for name, digest in HASHES.items():
        assert hashlib.sha256((oracle / name).read_bytes()).hexdigest() == digest, name
    tree = ast.parse((oracle / "sense.py").read_text())
    clock = SimpleNamespace(time=lambda: 0)
    namespace = {"struct": struct, "umsgpack": umsgpack, "time": clock,
                 "Sensor": SimpleNamespace(SID_TIME=1)}

    def method(class_name, name):
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
        function = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "pinned-sense.py", "exec"), namespace)
        return namespace[name]

    pack = method("Location", "pack")
    unpack = method("Location", "unpack")
    packed = method("Telemeter", "packed")
    fixture = json.loads((Path(__file__).resolve().parents[1] /
        "crates/r3akt-map-core/tests/fixtures/sideband_pyxis.json").read_text())
    probe = ['#include "LocationTelemetryCodec.h"', '#include <cassert>',
             '#include <cstring>', 'int main() {']
    for vector in fixture["vectors"]:
        data = {key: vector[key] for key in ["latitude", "longitude", "altitude", "bearing", "accuracy"]}
        data.update(speed=vector["speed_kmh"], last_update=vector["location_timestamp_seconds"])
        sensor = SimpleNamespace(data=data, active=True, sid=2)
        sensor.pack = lambda sensor=sensor: pack(sensor)
        clock.time = lambda vector=vector: vector["sensor_timestamp_seconds"]
        encoded = packed(SimpleNamespace(sensors={"location": sensor}))
        assert encoded.hex() == vector["packed_hex"], vector["name"]
        decoded = unpack(sensor, umsgpack.unpackb(encoded)[2])
        assert decoded == data, vector["name"]
        expected = vector["expected_fixed"]
        values = [expected[key] for key in ["latitude_e6", "longitude_e6", "altitude_cm",
                  "speed_centi_kmh", "bearing_cdeg", "accuracy_cm"]]
        values += [vector["location_timestamp_seconds"], vector["sensor_timestamp_seconds"]]
        probe += ['{', 'using namespace Telemetry;',
                  'const uint8_t golden[] = {' + ','.join(str(b) for b in encoded) + '};',
                  'LocationTelemetry input{' + ','.join(str(v) for v in values) + '};',
                  'uint8_t output[96]; std::size_t written = 0;',
                  'assert(encodeLocationTelemetry(input, output, sizeof(output), written) == EncodeResult::OK);',
                  'assert(written == sizeof(golden) && std::memcmp(output, golden, written) == 0);',
                  'LocationTelemetry decoded;',
                  'assert(decodeLocationTelemetry(golden, sizeof(golden), decoded) == DecodeResult::OK);',
                  'assert(decoded.altitude_cm == input.altitude_cm);',
                  'assert(decoded.speed_centi_kmh == input.speed_centi_kmh);',
                  'assert(decoded.timestamp_seconds == input.timestamp_seconds);', '}']
    probe += ['}']
    with tempfile.TemporaryDirectory(prefix="telemeter-oracle-") as directory:
        directory = Path(directory)
        source = directory / "probe.cpp"
        source.write_text("\n".join(probe))
        binary = directory / "probe"
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(oracle),
                        str(source), str(oracle / "LocationTelemetryCodec.cpp"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print("PASS: five synthetic vectors, exact Sideband methods and Pyxis C++ codec, both directions")


if __name__ == "__main__":
    main()
