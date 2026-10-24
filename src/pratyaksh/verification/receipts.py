"""Verification Receipts: Ed25519-signed statements of a closed Call's result.

Internal to the Verifier. A receipt is a compact JWS (a JWT with alg EdDSA), so the bank's core
systems can check it with any JWT library and the public key from GET /v1/receipts/key before
they act on a Request.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

log = logging.getLogger(__name__)


class InvalidReceipt(ValueError):
    pass


class ReceiptSigner:
    def __init__(self, key: Ed25519PrivateKey):
        self._key = key
        self._public = key.public_key()
        raw = self._public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self._x = _b64(raw)
        self.kid = hashlib.sha256(raw).hexdigest()[:16]

    @classmethod
    def generate(cls) -> "ReceiptSigner":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path: str | Path) -> "ReceiptSigner":
        """The signing key at path; a new one is created there (readable by this user only) if missing."""
        p = Path(path)
        if p.exists():
            key = serialization.load_pem_private_key(p.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise InvalidReceipt(f"{p} is not an Ed25519 private key")
            return cls(key)
        key = Ed25519PrivateKey.generate()
        p.parent.mkdir(parents=True, exist_ok=True)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        signer = cls(key)
        log.info("created Verification Receipt signing key %s (kid %s)", p, signer.kid)
        return signer

    def public_jwk(self) -> dict:
        return {"kty": "OKP", "crv": "Ed25519", "x": self._x, "kid": self.kid, "alg": "EdDSA", "use": "sig"}

    def sign(self, claims: dict) -> str:
        header = {"alg": "EdDSA", "typ": "JWT", "kid": self.kid}
        signing_input = f"{_b64(_json(header))}.{_b64(_json(claims))}"
        return f"{signing_input}.{_b64(self._key.sign(signing_input.encode()))}"

    def verify(self, token: str) -> dict:
        """The claims, if the signature is ours. Raises InvalidReceipt otherwise."""
        try:
            head, body, sig = token.strip().split(".")
            header = json.loads(_unb64(head))
            if header.get("alg") != "EdDSA" or header.get("kid") != self.kid:
                raise InvalidReceipt("not signed with this verifier's key")
            self._public.verify(_unb64(sig), f"{head}.{body}".encode())
            return json.loads(_unb64(body))
        except InvalidReceipt:
            raise
        except (InvalidSignature, ValueError, TypeError, AttributeError) as e:
            raise InvalidReceipt("signature does not match") from e


def _json(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
