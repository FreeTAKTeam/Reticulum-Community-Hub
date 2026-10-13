#!/usr/bin/env python3
"""Execute Columba's pinned, unmodified codec against the synthetic RCH fixture.

Requires a Columba checkout, Kotlin JVM compiler classpath and the pinned
MessagePack/stdlib jars. It downloads nothing and needs no Android device.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

PIN = "a402ed1052ba6993454352ce51ddfc336b729d9f"
MODEL = """package network.columba.app.rns.api.model
data class LocationTelemetry(val lat: Double,val lng: Double,val acc: Float,val ts: Long,
val altitude: Double=0.0,val speed: Double=0.0,val bearing: Double=0.0,val cease: Boolean=false,
val expires: Long?=null,val approxRadius: Int=0)
"""
PROBE = """import network.columba.app.rns.api.model.LocationTelemetry
import network.columba.app.rns.api.util.TelemeterCodec
fun main() {
 val input=LocationTelemetry(lat=0.0,lng=0.0,acc=5.0f,ts=1700000000000L,
 altitude=-12.5,speed=1.25,bearing=-1.5)
 val packed=TelemeterCodec.packLocationTelemetry(input)
 check(TelemeterCodec.unpackLocationTelemetry(packed)==input)
 check(TelemeterCodec.telemetryRequestTimebaseSeconds(input.ts)==1700000000L)
 check(TelemeterCodec.telemetryRequestTimebaseSeconds(null)==0L)
 println(java.util.Base64.getEncoder().encodeToString(packed))
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--columba-root", type=Path, required=True)
    parser.add_argument("--compiler-classpath", required=True)
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--msgpack-jar", type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(args.columba_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PIN:
        raise SystemExit(f"Columba revision mismatch: expected {PIN}")
    codec_relative = "rns-api/src/main/java/network/columba/app/rns/api/util/TelemeterCodec.kt"
    codec = args.columba_root / codec_relative
    source = subprocess.check_output(["git", "-C", str(args.columba_root), "show", f"{PIN}:{codec_relative}"])
    if codec.read_bytes() != source:
        raise SystemExit("Columba codec has local changes; refusing an unpinned result")
    fixture = json.loads((Path(__file__).resolve().parents[1] /
        "crates/r3akt-map-core/tests/fixtures/columba_2_2_6.json").read_text())
    with tempfile.TemporaryDirectory(prefix="rch-columba-codec-") as directory:
        output = Path(directory)
        model = output / "LocationTelemetry.kt"
        probe = output / "Probe.kt"
        model.write_text(MODEL)
        probe.write_text(PROBE)
        classpath = f"{args.msgpack_jar}:{args.stdlib}"
        subprocess.run([
            "java", "-cp", args.compiler_classpath, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
            "-no-stdlib", "-no-reflect", "-classpath", classpath, "-d", str(output / "classes"),
            str(model), str(codec), str(probe),
        ], check=True)
        encoded = subprocess.check_output([
            "java", "-cp", f"{output / 'classes'}:{classpath}", "ProbeKt",
        ], text=True).strip()
        if encoded != fixture["packed_telemeter_b64"]:
            raise SystemExit("Columba codec bytes differ from committed synthetic fixture")
    print("PASS: Columba 2.2.6 exact codec, signed readings, roundtrip and seconds timebase")


if __name__ == "__main__":
    main()
