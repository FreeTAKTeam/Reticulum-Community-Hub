"""Marker identity helpers for Reticulum-backed marker objects."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Optional

import RNS
import RNS.vendor.umsgpack as msgpack
from dotenv import load_dotenv as load_env
from RNS.Cryptography import Token

from .models import Marker


MARKER_IDENTITY_ENV_KEY = "RTH_MARKER_IDENTITY_KEY"
_cached_tokens: dict[bytes, Token] = {}


def derive_marker_identity_key(identity: RNS.Identity) -> bytes:
    """Derive an encryption key from the hub identity.

    Args:
        identity (RNS.Identity): Hub identity.

    Returns:
        bytes: 32-byte encryption key derived from the identity.
    """

    private_key = identity.get_private_key()
    if not private_key:
        raise ValueError("Hub identity is missing a private key.")
    return hashlib.sha256(private_key).digest()


def load_or_generate_identity(identity_path: Path) -> RNS.Identity:
    """Load a Reticulum identity or generate one if missing.

    Args:
        identity_path (Path): Filesystem path for the identity.

    Returns:
        RNS.Identity: Loaded or newly created identity.
    """

    identity_path = Path(identity_path)
    if identity_path.exists():
        try:
            return RNS.Identity.from_file(str(identity_path))
        except Exception:
            pass
    identity = RNS.Identity()
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity.to_file(str(identity_path))
    return identity


def derive_marker_identity_key_from_path(identity_path: Path) -> bytes:
    """Derive an encryption key from an identity on disk.

    Args:
        identity_path (Path): Filesystem path for the identity.

    Returns:
        bytes: Derived 32-byte encryption key.
    """

    identity = load_or_generate_identity(identity_path)
    return derive_marker_identity_key(identity)


def _load_marker_identity_key() -> bytes:
    """Return the marker identity encryption key from the environment.

    Returns:
        bytes: Raw encryption key bytes.

    Raises:
        ValueError: When the key is missing or invalid.
    """

    load_env()
    raw_key = os.environ.get(MARKER_IDENTITY_ENV_KEY, "").strip()
    if not raw_key:
        raise ValueError(
            f"{MARKER_IDENTITY_ENV_KEY} must be set to a hex-encoded key."
        )
    try:
        key_bytes = bytes.fromhex(raw_key)
    except ValueError as exc:
        raise ValueError(
            f"{MARKER_IDENTITY_ENV_KEY} must be hex-encoded."
        ) from exc
    if len(key_bytes) not in (32, 64):
        raise ValueError(
            f"{MARKER_IDENTITY_ENV_KEY} must be 32 or 64 bytes when decoded."
        )
    return key_bytes


def _get_marker_identity_token(identity_key: Optional[bytes] = None) -> Token:
    """Return a cached Token for marker identity encryption.

    Args:
        identity_key (Optional[bytes]): Optional key override.

    Returns:
        Token: Token configured with the marker identity key.
    """

    key_bytes = identity_key or _load_marker_identity_key()
    cached = _cached_tokens.get(key_bytes)
    if cached is not None:
        return cached
    token = Token(key_bytes)
    _cached_tokens[key_bytes] = token
    return token


def encrypt_marker_identity(identity: RNS.Identity, *, identity_key: Optional[bytes] = None) -> str:
    """Encrypt and encode a marker identity private key.

    Args:
        identity (RNS.Identity): Identity to encrypt.
        identity_key (Optional[bytes]): Optional key override.

    Returns:
        str: Base64-encoded encrypted private key.
    """

    token = _get_marker_identity_token(identity_key=identity_key)
    encrypted = token.encrypt(identity.get_private_key())
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_marker_identity(
    storage_key: str, *, identity_key: Optional[bytes] = None
) -> RNS.Identity:
    """Decode and decrypt a stored marker identity key.

    Args:
        storage_key (str): Base64-encoded encrypted identity key.
        identity_key (Optional[bytes]): Optional key override.

    Returns:
        RNS.Identity: Decrypted Reticulum identity.

    Raises:
        ValueError: When the identity cannot be reconstructed.
    """

    token = _get_marker_identity_token(identity_key=identity_key)
    raw = base64.b64decode(storage_key.encode("ascii"))
    private_key = token.decrypt(raw)
    identity = RNS.Identity.from_bytes(private_key)
    if identity is None:
        raise ValueError("Failed to reconstruct marker identity from storage key.")
    return identity


def marker_destination_hash(identity: RNS.Identity) -> str:
    """Return the destination hash for a marker identity.

    Args:
        identity (RNS.Identity): Marker identity to hash.

    Returns:
        str: Lowercase hex destination hash.
    """

    destination_hash = RNS.Destination.hash(identity, "lxmf", "delivery")
    return destination_hash.hex().lower()


def build_marker_destination(identity: RNS.Identity) -> RNS.Destination:
    """Create an inbound LXMF destination for a marker identity.

    Args:
        identity (RNS.Identity): Identity for the destination.

    Returns:
        RNS.Destination: Configured inbound destination.
    """

    return RNS.Destination(
        identity,
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )


def build_marker_announce_data(marker: Marker) -> bytes:
    """Build announce application data for a marker object.

    Args:
        marker (Marker): Marker metadata to include.

    Returns:
        bytes: Msgpack-encoded announce payload.
    """

    display_name = marker.name.encode("utf-8") if marker.name else None
    metadata = {
        "display_name": marker.name,
        "is_object": True,
        "object_type": "marker",
        "marker_type": marker.marker_type,
        "symbol": marker.symbol,
    }
    return msgpack.packb([display_name, None, metadata])
