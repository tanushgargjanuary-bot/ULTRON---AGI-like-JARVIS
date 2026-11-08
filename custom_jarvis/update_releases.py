"""Validate signed release metadata before a future staged updater uses it.

This module is deliberately not a downloader or installer. It validates a
per-user update-channel preference, verifies an Ed25519-signed manifest against
public keys pinned by the caller, and checks a staged artifact's size and SHA-256.
No key from the downloaded manifest is trusted, and no release code is executed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CHANNELS = frozenset({"stable", "owner-canary"})
MAX_ARTIFACT_SIZE = 4 * 1024 * 1024 * 1024
_POLICY_SCHEMA = 1
_PAYLOAD_FIELDS = frozenset({
    "schema_version", "channel", "version", "source_commit", "platform",
    "asset_name", "artifact_sha256", "artifact_size",
})
_VERSION = re.compile(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_PLATFORM = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class ReleaseValidationError(ValueError):
    """A policy, manifest, signature, or staged-artifact check failed."""


@dataclass(frozen=True)
class UpdatePolicy:
    """Per-installation update preference; not an identity or access control."""

    channel: str = "stable"
    automatic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.channel, str) or self.channel not in CHANNELS:
            raise ReleaseValidationError("unknown update channel")
        if not isinstance(self.automatic, bool):
            raise ReleaseValidationError("automatic must be a boolean")


def load_update_policy(path: Path | str) -> UpdatePolicy:
    """Read the local policy; missing means stable/manual, malformed fails closed."""
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return UpdatePolicy()
    except (OSError, UnicodeError) as error:
        raise ReleaseValidationError(f"could not read update policy: {error}") from error

    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ReleaseValidationError("update policy is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "schema_version", "channel", "automatic"
    }:
        raise ReleaseValidationError("update policy has an unexpected shape")
    if type(document["schema_version"]) is not int or document["schema_version"] != _POLICY_SCHEMA:
        raise ReleaseValidationError("unsupported update-policy schema")
    return UpdatePolicy(channel=document["channel"], automatic=document["automatic"])


def save_update_policy(path: Path | str, policy: UpdatePolicy) -> None:
    """Atomically save a local preference without storing credentials or keys."""
    if not isinstance(policy, UpdatePolicy):
        raise ReleaseValidationError("policy must be an UpdatePolicy")
    target = Path(path)
    temporary = target.with_name(target.name + ".tmp")
    document = {
        "schema_version": _POLICY_SCHEMA,
        "channel": policy.channel,
        "automatic": policy.automatic,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ReleaseValidationError(f"could not save update policy: {error}") from error


def canonical_payload(payload: Mapping) -> bytes:
    """The exact UTF-8 bytes that release signing and verification must share."""
    try:
        return json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ReleaseValidationError("release payload cannot be canonicalized") from error


@dataclass(frozen=True)
class VerifiedRelease:
    """Validated manifest fields; this does not mean the artifact is installed."""

    channel: str
    version: str
    source_commit: str
    platform: str
    asset_name: str
    artifact_sha256: str
    artifact_size: int
    key_id: str


def verify_release_manifest(
    document: Mapping,
    trusted_keys: Mapping[str, bytes],
    *,
    selected_channel: str,
    expected_platform: str,
) -> VerifiedRelease:
    """Validate schema, channel, platform and pinned Ed25519 signature.

    `trusted_keys` must come from a separately trusted local source. The manifest
    cannot add or replace keys. The caller must still verify the downloaded
    artifact with :func:`verify_artifact` before extraction or activation.
    """
    if not isinstance(selected_channel, str) or selected_channel not in CHANNELS:
        raise ReleaseValidationError("unknown selected update channel")
    if not isinstance(expected_platform, str) or not _PLATFORM.fullmatch(expected_platform):
        raise ReleaseValidationError("invalid expected platform")
    if not isinstance(trusted_keys, Mapping):
        raise ReleaseValidationError("trusted keys must come from a local keyring")
    if not isinstance(document, Mapping) or set(document) != {
        "payload", "key_id", "signature"
    }:
        raise ReleaseValidationError("release manifest has an unexpected shape")

    payload = document["payload"]
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_FIELDS:
        raise ReleaseValidationError("release payload has an unexpected shape")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ReleaseValidationError("unsupported release-manifest schema")

    channel = payload["channel"]
    version = payload["version"]
    source_commit = payload["source_commit"]
    platform = payload["platform"]
    asset_name = payload["asset_name"]
    digest = payload["artifact_sha256"]
    size = payload["artifact_size"]

    if (not isinstance(channel, str) or channel not in CHANNELS
            or channel != selected_channel):
        raise ReleaseValidationError("release channel does not match local policy")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ReleaseValidationError("release version is malformed")
    if (not isinstance(source_commit, str) or not _COMMIT.fullmatch(source_commit)
            or set(source_commit) == {"0"}):
        raise ReleaseValidationError("source commit must be a full Git object id")
    if (not isinstance(platform, str) or not _PLATFORM.fullmatch(platform)
            or platform != expected_platform):
        raise ReleaseValidationError("release is for a different or invalid platform")
    if not isinstance(asset_name, str) or not _ASSET_NAME.fullmatch(asset_name):
        raise ReleaseValidationError("artifact name must be a plain safe file name")
    if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
        raise ReleaseValidationError("artifact SHA-256 is malformed")
    if (type(size) is not int or size <= 0 or size > MAX_ARTIFACT_SIZE):
        raise ReleaseValidationError("artifact size is outside the permitted range")

    key_id = document["key_id"]
    signature_text = document["signature"]
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise ReleaseValidationError("release signing key id is malformed")
    public_bytes = trusted_keys.get(key_id)
    if not isinstance(public_bytes, bytes):
        raise ReleaseValidationError("release signing key is not trusted on this installation")
    if not isinstance(signature_text, str):
        raise ReleaseValidationError("release signature is malformed")
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(signature, canonical_payload(payload))
    except (binascii.Error, ValueError, InvalidSignature) as error:
        raise ReleaseValidationError("release signature verification failed") from error

    return VerifiedRelease(
        channel=channel,
        version=version,
        source_commit=source_commit,
        platform=platform,
        asset_name=asset_name,
        artifact_sha256=digest,
        artifact_size=size,
        key_id=key_id,
    )


def verify_artifact(path: Path | str, release: VerifiedRelease) -> None:
    """Stream-check staged bytes before extraction; reject symlinks and mismatches."""
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file():
            raise ReleaseValidationError("staged artifact is not a regular file")
        if target.stat().st_size != release.artifact_size:
            raise ReleaseValidationError("staged artifact size does not match the signed manifest")
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ReleaseValidationError(f"could not verify staged artifact: {error}") from error
    if digest.hexdigest() != release.artifact_sha256:
        raise ReleaseValidationError("staged artifact SHA-256 does not match the signed manifest")
