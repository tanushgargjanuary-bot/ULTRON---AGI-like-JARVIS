"""Offline tests for release-manifest verification and local update-channel policy."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custom_jarvis.update_releases import (
    ReleaseValidationError,
    UpdatePolicy,
    canonical_payload,
    load_update_policy,
    save_update_policy,
    verify_artifact,
    verify_release_manifest,
)


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_bytes = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.key_id = "test-release-key"
        self.trusted_keys = {self.key_id: self.public_bytes}
        artifact = b"signed test release bytes"
        self.artifact_bytes = artifact
        self.payload = {
            "schema_version": 1,
            "channel": "owner-canary",
            "version": "v1.2.3-rc.1",
            "source_commit": "a" * 40,
            "platform": "windows-x86_64",
            "asset_name": "ultron-windows-x86_64.zip",
            "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
            "artifact_size": len(artifact),
        }
        self.document = self._signed_document(self.payload)

    def _signed_document(self, payload):
        signature = self.private_key.sign(canonical_payload(payload))
        return {
            "payload": dict(payload),
            "key_id": self.key_id,
            "signature": base64.b64encode(signature).decode("ascii"),
        }

    def _verify(self, document=None, **kwargs):
        return verify_release_manifest(
            document or self.document,
            self.trusted_keys,
            selected_channel=kwargs.get("selected_channel", "owner-canary"),
            expected_platform=kwargs.get("expected_platform", "windows-x86_64"),
        )

    def test_valid_manifest_is_verified_against_local_key(self):
        release = self._verify()
        self.assertEqual(release.version, "v1.2.3-rc.1")
        self.assertEqual(release.source_commit, "a" * 40)
        self.assertEqual(release.key_id, self.key_id)

    def test_manifest_cannot_choose_a_new_trust_key(self):
        with self.assertRaisesRegex(ReleaseValidationError, "not trusted"):
            verify_release_manifest(
                self.document,
                {},
                selected_channel="owner-canary",
                expected_platform="windows-x86_64",
            )

    def test_tampered_payload_fails_signature(self):
        tampered = dict(self.document)
        tampered["payload"] = dict(self.payload, version="v9.9.9")
        with self.assertRaisesRegex(ReleaseValidationError, "signature verification failed"):
            self._verify(tampered)

    def test_wrong_channel_or_platform_is_rejected(self):
        with self.assertRaisesRegex(ReleaseValidationError, "channel"):
            self._verify(selected_channel="stable")
        with self.assertRaisesRegex(ReleaseValidationError, "platform"):
            self._verify(expected_platform="windows-arm64")

    def test_malformed_fields_are_rejected_before_activation(self):
        for field, value in (
            ("source_commit", "short"),
            ("asset_name", "..\\outside.zip"),
            ("artifact_sha256", "not-a-hash"),
            ("artifact_size", True),
        ):
            with self.subTest(field=field):
                payload = dict(self.payload, **{field: value})
                with self.assertRaises(ReleaseValidationError):
                    self._verify(self._signed_document(payload))

    def test_staged_artifact_must_match_signed_size_and_hash(self):
        release = self._verify()
        with tempfile.TemporaryDirectory() as temp:
            artifact_path = Path(temp) / release.asset_name
            artifact_path.write_bytes(self.artifact_bytes)
            verify_artifact(artifact_path, release)
            artifact_path.write_bytes(b"modified bytes")
            with self.assertRaisesRegex(ReleaseValidationError, "size does not match"):
                verify_artifact(artifact_path, release)

    def test_same_size_artifact_tampering_is_detected(self):
        release = self._verify()
        with tempfile.TemporaryDirectory() as temp:
            artifact_path = Path(temp) / release.asset_name
            artifact_path.write_bytes(b"x" * release.artifact_size)
            with self.assertRaisesRegex(ReleaseValidationError, "SHA-256"):
                verify_artifact(artifact_path, release)


class UpdatePolicyTests(unittest.TestCase):
    def test_missing_policy_defaults_to_stable_manual(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = load_update_policy(Path(temp) / "missing.json")
        self.assertEqual(policy, UpdatePolicy())

    def test_owner_canary_policy_round_trips_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state" / "update-policy.json"
            selected = UpdatePolicy(channel="owner-canary", automatic=True)
            save_update_policy(path, selected)
            self.assertEqual(load_update_policy(path), selected)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_corrupt_policy_fails_closed_with_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update-policy.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "not valid"):
                load_update_policy(path)

    def test_unknown_channel_and_non_boolean_auto_flag_are_rejected(self):
        with self.assertRaises(ReleaseValidationError):
            UpdatePolicy(channel="anything-else", automatic=True)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update-policy.json"
            path.write_text(json.dumps({
                "schema_version": 1, "channel": "stable", "automatic": 1,
            }), encoding="utf-8")
            with self.assertRaises(ReleaseValidationError):
                load_update_policy(path)


if __name__ == "__main__":
    unittest.main()
