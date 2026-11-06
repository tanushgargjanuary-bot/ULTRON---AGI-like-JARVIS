"""Deterministic repair applicability, not model confidence or authorization.

Fingerprints avoid persisting raw reviewed arguments. They are not encryption or
protection against an attacker who can edit the ledger and adapter together.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from custom_jarvis.repair_adapter import AdapterError, bounded

POLICY_VERSION = 1
DEFAULT_LIFETIME = 7 * 24 * 60 * 60


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            bounded(value), sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


@lru_cache(maxsize=32)
def _compiled_validator(encoded_schema: str):
    # Lazy import: ordinary native startup does not need the repair validator.
    # Parse an owned snapshot so later caller mutations cannot change a cached
    # validator. Content keys invalidate on nested schema edits, not just identity.
    from jsonschema import Draft202012Validator

    schema = json.loads(encoded_schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_arguments(arguments: dict, schema: dict | None) -> None:
    if schema is None:
        return  # Unbound library tests; the application always supplies a schema.
    from jsonschema.exceptions import SchemaError, ValidationError

    try:
        encoded = json.dumps(
            schema, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
        _compiled_validator(encoded).validate(arguments)
        # Tool handlers cannot accept arbitrary extra kwargs even if their JSON
        # schema omitted additionalProperties=false.
        if set(arguments) - set(schema.get("properties", {})):
            raise AdapterError("Adapted output contains an undeclared tool argument")
    except AdapterError:
        raise
    except (SchemaError, ValidationError, TypeError, ValueError) as exc:
        raise AdapterError(
            "Adapted arguments do not satisfy the registered tool schema"
        ) from exc


@dataclass(frozen=True)
class RepairDecision:
    action: str
    reason: str
    version: str | None = None

    def to_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason, "version": self.version}


def judge(
    entry: dict | None, arguments: dict, context_key: str, now: float | None = None
) -> RepairDecision:
    if entry is None:
        return RepairDecision("no_repair", "NO_ACTIVE_REPAIR")
    version = entry["current"]
    scope = entry.get("judgment")
    if not isinstance(scope, dict) or scope.get("policy_version") != POLICY_VERSION:
        return RepairDecision("abstain", "LEGACY_OR_UNKNOWN_POLICY", version)
    if entry.get("quarantined"):
        return RepairDecision("abstain", "QUARANTINED_NEEDS_REVIEW", version)
    expiry = scope.get("expires_at")
    if type(expiry) not in (int, float) or not 0 < expiry < float("inf"):
        return RepairDecision("abstain", "INVALID_EXPIRY", version)
    if (time.time() if now is None else now) >= expiry:
        return RepairDecision("abstain", "REVIEW_EXPIRED", version)
    if scope.get("context_key") != context_key:
        return RepairDecision(
            "abstain", "WORKSPACE_SCHEMA_OR_IMPLEMENTATION_CHANGED", version
        )
    approved = scope.get("approved_inputs")
    key = fingerprint(arguments)
    if not isinstance(approved, dict) or key not in approved:
        return RepairDecision("abstain", "UNREVIEWED_INPUT", version)
    if approved[key] == key:
        return RepairDecision("abstain", "REVIEWED_NO_CHANGE", version)
    return RepairDecision("apply", "EXACT_REVIEWED_CONTRACT", version)
