from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from packages.core.config import build_settings


class SecretStore(Protocol):
    def put(self, plaintext: str, *, secret_ref: str | None = None) -> str:
        ...

    def get(self, secret_ref: str) -> str | None:
        ...

    def disable(self, secret_ref: str) -> None:
        ...


def local_dev_secret_envelope(value: str) -> str:
    return "dev+base64:" + base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def open_local_dev_secret_envelope(value: str) -> str:
    prefix = "dev+base64:"
    if not value.startswith(prefix):
        raise ValueError("Unsupported local secret envelope.")
    return base64.urlsafe_b64decode(value[len(prefix) :].encode("ascii")).decode("utf-8")


class SecretCipher:
    envelope_prefix = "fernet:v1:"

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_store(cls, secret_store: SecretStore) -> "SecretCipher":
        configured = os.getenv("CUTAGENT_SECRET_ENCRYPTION_KEY")
        if configured:
            return cls(_coerce_fernet_key(configured))
        root = Path(getattr(secret_store, "root", build_settings().secret_store.dir))
        key_path = root / ".db_encryption_key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip().encode("ascii")
        else:
            key = Fernet.generate_key()
            key_path.write_text(key.decode("ascii"), encoding="utf-8")
            key_path.chmod(0o600)
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{self.envelope_prefix}{token}"

    def decrypt(self, envelope: str) -> str | None:
        if not envelope.startswith(self.envelope_prefix):
            return None
        token = envelope[len(self.envelope_prefix) :].encode("ascii")
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError):
            return None


def _coerce_fernet_key(value: str) -> bytes:
    key = value.strip().encode("ascii")
    Fernet(key)
    return key


class LocalSecretStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or build_settings().secret_store.dir)

    def put(self, plaintext: str, *, secret_ref: str | None = None) -> str:
        ref = secret_ref or f"sec_{uuid4().hex}.secret"
        path = self._path(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(local_dev_secret_envelope(plaintext), encoding="utf-8")
        path.chmod(0o600)
        return ref

    def get(self, secret_ref: str) -> str | None:
        path = self._path(secret_ref)
        if not path.exists():
            return None
        return open_local_dev_secret_envelope(path.read_text(encoding="utf-8"))

    def disable(self, secret_ref: str) -> None:
        path = self._path(secret_ref)
        if path.exists():
            path.unlink()

    def _path(self, secret_ref: str) -> Path:
        if "/" in secret_ref or "\\" in secret_ref:
            raise ValueError("secret_ref must be a file name, not a path.")
        return self.root / secret_ref
