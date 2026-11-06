"""crypto_ident — what is this string, and what is this file?

Recognition, not decryption. Given a token or a blob it says which format it looks
like and why, decodes what is safe to decode (a JWT's header and payload are
base64, and reading them is not an attack), and refuses to imply that a signature
has been checked when it has not.
"""

import base64
import binascii
import json
import re

PLUGIN = {
    "name": "crypto_ident",
    "description": (
        "Identifies a token, hash or encoded blob: JWT, base64, hex, a known hash "
        "format, or a file type from its first bytes. It decodes a JWT header and "
        "payload WITHOUT verifying the signature and says so. Use it when the user "
        "pastes an unknown string and asks what it is."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "The string to identify"},
        },
        "required": ["text"],
    },
    "tier": "ROUTINE",
}

_HASHES = [(32, "MD5"), (40, "SHA-1"), (56, "SHA-224 / SHA3-224"),
           (64, "SHA-256 / SHA3-256 / BLAKE2s"), (96, "SHA-384"), (128, "SHA-512")]

_MAGIC = [(b"\x89PNG", "PNG image"), (b"\xff\xd8\xff", "JPEG image"),
          (b"%PDF", "PDF document"), (b"PK\x03\x04", "ZIP archive or an Office file"),
          (b"\x1f\x8b", "gzip archive"), (b"\x7fELF", "ELF binary"),
          (b"MZ", "Windows executable"), (b"GIF8", "GIF image"),
          (b"SQLite format 3", "SQLite database"), (b"\x00\x00\x01\x00", "ICO icon")]


def _jwt(text):
    parts = text.split(".")
    if len(parts) != 3:
        return None
    def decode(segment):
        padded = segment + "=" * (-len(segment) % 4)
        try:
            return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
    header, payload = decode(parts[0]), decode(parts[1])
    if not isinstance(header, dict):
        return None
    return header, payload


def run(parameters, player=None, session_memory=None):
    text = str(parameters.get("text") or "").strip()
    if not text:
        return "There is nothing to identify."

    jwt = _jwt(text)
    if jwt:
        header, payload = jwt
        return (f"That is a JWT. Header: {json.dumps(header)[:300]}. "
                f"Payload: {json.dumps(payload)[:600]}. "
                "I have NOT checked the signature — reading a JWT is not verifying it.")

    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text):
        # Checked before base64, because a UUID is valid base64 and was being
        # reported as "27 bytes of base64" — true and useless.
        return (f"That is a UUID (version {text[14]}, variant {text[19]}). "
                "It identifies a record; it is not a secret and not a hash.")

    if re.fullmatch(r"[0-9a-fA-F]+", text):
        for length, name in _HASHES:
            if len(text) == length:
                return (f"That looks like {name}: {length} hex characters. "
                        "I cannot tell which algorithm from the shape alone.")
        return f"That is hex, {len(text)} characters ({len(text) // 2} bytes)."

    if text.count(".") == 2 and len(text) > 40:
        return "That has three parts and looks like a JWT, but it does not decode."

    if re.fullmatch(r"[A-Za-z0-9+/=_-]{16,}", text):
        try:
            padded = text + "=" * (-len(text) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            printable = sum(1 for b in raw if 32 <= b < 127) / max(1, len(raw))
            if printable > 0.85:
                return f"That is base64 for: {raw.decode('utf-8', 'replace')[:300]}"
            return (f"That is base64, {len(raw)} bytes, and not mostly text "
                    f"(starts with {raw[:8].hex()}).")
        except (binascii.Error, ValueError):
            pass

    if text.startswith("-----BEGIN"):
        label = text.splitlines()[0].strip("- ").strip()
        return f"That is a PEM block: {label}. I will not decode private key material."
    return f"I do not recognise that format ({len(text)} characters)."
