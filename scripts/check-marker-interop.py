#!/usr/bin/env python3
"""Execute pinned Sideband and Columba receive methods on shared marker bytes.

Platform services are replaced with recording sinks; this is source-level
interoperability evidence, not an Android UI or radio test. Downloads nothing.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace

from RNS.vendor import umsgpack


def method(path, class_name, method_name, namespace):
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[method_name]


def sideband(oracle, stream):
    # sense.py is the reference already pinned by check-sideband-pyxis-fixtures.
    assert hashlib.sha256((oracle / "sense.py").read_bytes()).hexdigest() == "a1bcc2aee3234eae6e93a693ded9590e0edbc11350787f692fd7d3e2dfa76470"
    assert hashlib.sha256((oracle / "sideband-core.py").read_bytes()).hexdigest() == "a3b86201ad98022aa8e17db3ae7bde840164c45cf09f1601b6b21904f984a3b5"
    namespace = {"struct": struct, "umsgpack": umsgpack}
    unpack = method(oracle / "sense.py", "Location", "unpack", namespace)
    information = method(oracle / "sense.py", "Information", "unpack", namespace)
    import RNS
    namespace.update(RNS=RNS, LXMF=SimpleNamespace(
        FIELD_TELEMETRY=2, FIELD_TELEMETRY_STREAM=3, FIELD_ICON_APPEARANCE=4,
        FIELD_IMAGE=6, FIELD_AUDIO=7, FIELD_FILE_ATTACHMENTS=5))
    receive = method(oracle / "sideband-core.py", "SidebandCore", "_db_save_lxm", namespace)
    saved, appearances, persistent = [], [], {}

    def save(source, packed, **kwargs):
        sensors = umsgpack.unpackb(packed)
        decoded = unpack(None, sensors[2])
        assert decoded["latitude"] == 44.5 and decoded["longitude"] == -1.25
        assert decoded["last_update"] == 1700000000
        assert information(None, sensors[15])["contents"] == "Ridge\nSynthetic marker"
        saved.append((source, kwargs["via"]))
        return packed

    peer = bytes.fromhex("bb" * 16)
    sink = SimpleNamespace(config={"telemetry_receive_trusted_only": False},
        _db_save_telemetry=save,
        _db_update_appearance=lambda *args, **kwargs: appearances.append(args),
        getpersistent=persistent.get, setpersistent=persistent.__setitem__, is_trusted=lambda _: False)
    message = SimpleNamespace(state=0, fields={3: stream}, content=b"", title=b"")
    receive(sink, message, peer)
    assert saved == [(stream[0][0], peer)] and saved[0][0] != peer
    assert appearances[0][0] == stream[0][0]
    assert appearances[0][2][0] == "fire"
    sink.config["telemetry_receive_trusted_only"] = True
    receive(sink, message, peer)
    assert len(saved) == 1, "existing Sideband trust policy must still apply"


def columba(args, fixture):
    spec = importlib.util.spec_from_file_location("columba_oracle", Path(__file__).with_name("check-columba-telemetry-fixture.py"))
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    root = args.columba_root
    assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == oracle.PIN
    path = "rns-backend-kt/src/main/kotlin/network/columba/app/rns/backend/kt/NativeTelemetryHandler.kt"
    source = subprocess.check_output(["git", "-C", str(root), "show", f"{oracle.PIN}:{path}"], text=True)
    # Preserve the actual receive methods, including source identity/time handling.
    methods = source[source.index("    fun unpackLocationTelemetryField"):source.index("    fun extractIconAppearance")]
    probe = '''import org.json.JSONObject
import org.msgpack.core.MessagePack
import network.columba.app.rns.api.util.TelemeterCodec
fun ByteArray.toHex() = joinToString("") { "%02x".format(it.toInt() and 255) }
object Receiver {
 const val LOCATION_SHARE_TYPE = "location_share"
 METHODS
 fun decode(entry: List<*>) = unpackTelemetryStreamEntry(entry)
}
fun main() {
 val bytes = "STREAM".chunked(2).map { it.toInt(16).toByte() }.toByteArray()
 val p = MessagePack.newDefaultUnpacker(bytes)
 check(p.unpackArrayHeader() == 1); check(p.unpackArrayHeader() == 4)
 fun binary() = p.readPayload(p.unpackBinaryHeader())
 val source = binary(); val time = p.unpackLong(); val packed = binary()
 check(p.unpackArrayHeader() == 3)
 val appearance = listOf(p.unpackString(), binary(), binary())
 check(!p.hasNext())
 val decoded = Receiver.decode(listOf(source, time, packed, appearance))!!
 check(decoded.getString("source_hash") == "0123456789abcdef0123456789abcdef")
 check(decoded.getLong("ts") == 1700000000000L)
 check(decoded.getDouble("lat") == 44.5 && decoded.getDouble("lng") == -1.25)
 check(decoded.getDouble("speed") == 0.0 && decoded.getBoolean("relayed"))
 check(decoded.getJSONObject("appearance").getString("icon_name") == "fire")
 check(Receiver.decode(listOf(source, time, byteArrayOf(0xc1.toByte()), appearance)) == null)
 println("PASS: Columba marker stream identity, position, timestamp and icon")
}
'''.replace("METHODS", methods).replace("STREAM", fixture["stream_hex"])
    codec_path = "rns-api/src/main/java/network/columba/app/rns/api/util/TelemeterCodec.kt"
    codec = subprocess.check_output(["git", "-C", str(root), "show", f"{oracle.PIN}:{codec_path}"])
    with tempfile.TemporaryDirectory(prefix="marker-columba-") as directory:
        directory = Path(directory)
        (directory / "LocationTelemetry.kt").write_text(oracle.MODEL)
        (directory / "TelemeterCodec.kt").write_bytes(codec)
        (directory / "Probe.kt").write_text(probe)
        cp = f"{args.stdlib}:{args.msgpack_jar}:{args.json_jar}"
        subprocess.run(["java", "-cp", args.compiler_classpath, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
            "-no-stdlib", "-no-reflect", "-classpath", cp, "-d", str(directory / "classes"),
            *map(str, directory.glob("*.kt"))], check=True)
        subprocess.run(["java", "-cp", f"{directory / 'classes'}:{cp}", "ProbeKt"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--columba-root", type=Path, required=True)
    for name in ["compiler-classpath", "stdlib", "msgpack-jar", "json-jar"]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    fixture = json.loads((Path(__file__).resolve().parents[1] / "crates/r3akt-map-core/tests/fixtures/marker_stream.json").read_text())
    stream = umsgpack.unpackb(bytes.fromhex(fixture["stream_hex"]))
    sideband(args.oracle, stream)
    print("PASS: Sideband marker stream identity, position, timestamp, information, icon and trust gate")
    columba(args, fixture)


if __name__ == "__main__":
    main()
