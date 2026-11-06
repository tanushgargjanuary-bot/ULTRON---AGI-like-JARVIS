"""dev_hash — hashes, HMAC and base64, in one place.

Not a security product: this computes and compares hashes, which is what a
developer asks for a dozen times a day. Password hashing is deliberately absent —
`bcrypt`/`argon2` belong in the library that owns them, not in a voice assistant.
"""

import base64
import hashlib
import hmac

PLUGIN = {
    "name": "dev_hash",
    "description": (
        "Computes md5/sha1/sha256/sha512 digests, HMAC signatures, or encodes and "
        "decodes base64 and hex. Use it to check a checksum, compare two hashes, or "
        "convert text to base64. It does not hash passwords."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "digest | hmac | b64encode | b64decode | hexdecode"},
            "text": {"type": "STRING", "description": "The input"},
            "algorithm": {"type": "STRING",
                          "description": "md5 | sha1 | sha256 (default) | sha512"},
            "secret": {"type": "STRING", "description": "For action=hmac: the key"},
        },
        "required": ["action", "text"],
    },
    "tier": "ROUTINE",
}

_ALGORITHMS = {"md5": hashlib.md5, "sha1": hashlib.sha1,
               "sha256": hashlib.sha256, "sha512": hashlib.sha512}


def run(parameters, player=None, session_memory=None):
    action = str(parameters.get("action") or "digest").strip().lower()
    text = str(parameters.get("text") or "")
    algorithm = str(parameters.get("algorithm") or "sha256").strip().lower()
    if not text:
        return "There is nothing to hash."
    if algorithm not in _ALGORITHMS:
        return f"I know {', '.join(sorted(_ALGORITHMS))}. Not '{algorithm}'."

    try:
        if action == "digest":
            digest = _ALGORITHMS[algorithm](text.encode("utf-8")).hexdigest()
            return f"{algorithm} of {len(text)} bytes: {digest}"
        if action == "hmac":
            secret = str(parameters.get("secret") or "")
            if not secret:
                return "An HMAC needs a secret key."
            digest = hmac.new(secret.encode("utf-8"), text.encode("utf-8"), algorithm).hexdigest()
            return f"HMAC-{algorithm.upper()}: {digest}"
        if action == "b64encode":
            return base64.b64encode(text.encode("utf-8")).decode("ascii")
        if action == "b64decode":
            return base64.b64decode(text.encode("ascii"), validate=True).decode("utf-8", "replace")
        if action == "hexdecode":
            return bytes.fromhex(text).decode("utf-8", "replace")
    except Exception as exc:                                    # noqa: BLE001
        return f"That did not decode: {type(exc).__name__}: {exc}"
    return "I can compute a digest or HMAC, or encode and decode base64 and hex."
