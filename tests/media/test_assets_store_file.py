from __future__ import annotations

import hashlib
from datetime import timedelta

from packages.core.contracts import SignedUrlResponse, utcnow
from packages.core.storage.object_store import (
    ObjectRef,
    ObjectStore,
    StoredObject,
)
from packages.media.assets import store_file


class RecordingObjectStore(ObjectStore):
    def __init__(self) -> None:
        self.prepare_calls: list[tuple[str, str, str | None, str]] = []

    def prepare_upload(
        self,
        filename: str,
        purpose: str,
        *,
        content_key: str | None = None,
        tier: str = "durable",
    ) -> ObjectRef:
        self.prepare_calls.append((filename, purpose, content_key, tier))
        return ObjectRef(
            bucket=f"cutagent-{tier}",
            key=f"{purpose}/{filename}",
            uri=f"local://cutagent-{tier}/{purpose}/{filename}",
        )

    def put_bytes(self, ref: ObjectRef, content: bytes) -> StoredObject:
        return StoredObject(
            ref=ref,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def get_bytes(self, ref: ObjectRef) -> bytes:
        raise NotImplementedError

    def exists(self, ref: ObjectRef) -> bool:
        raise NotImplementedError

    def signed_url(
        self,
        uri: str,
        *,
        expires_in: timedelta = timedelta(minutes=15),
    ) -> SignedUrlResponse:
        return SignedUrlResponse(url=uri, expires_at=utcnow() + expires_in, request_id="req_test")


class CountingObjectStore(ObjectStore):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[ObjectRef] = []
        self.exists_calls: list[ObjectRef] = []
        self._sequence = 0

    def prepare_upload(
        self,
        filename: str,
        purpose: str,
        *,
        content_key: str | None = None,
        tier: str = "durable",
    ) -> ObjectRef:
        key_segment = content_key
        if key_segment is None:
            self._sequence += 1
            key_segment = f"upload-{self._sequence}"
        key = f"{purpose}/{key_segment}/{filename}"
        return ObjectRef(
            bucket=f"cutagent-{tier}",
            key=key,
            uri=f"local://cutagent-{tier}/{key}",
        )

    def put_bytes(self, ref: ObjectRef, content: bytes) -> StoredObject:
        self.put_calls.append(ref)
        self.objects[ref.uri] = content
        return StoredObject(
            ref=ref,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def get_bytes(self, ref: ObjectRef) -> bytes:
        return self.objects[ref.uri]

    def exists(self, ref: ObjectRef) -> bool:
        self.exists_calls.append(ref)
        return ref.uri in self.objects

    def signed_url(
        self,
        uri: str,
        *,
        expires_in: timedelta = timedelta(minutes=15),
    ) -> SignedUrlResponse:
        return SignedUrlResponse(url=uri, expires_at=utcnow() + expires_in, request_id="req_test")


def test_store_file_addressed_reuses_same_object_key_for_same_content(tmp_path):
    object_store = CountingObjectStore()
    source = tmp_path / "seed.mp4"
    source.write_bytes(b"same seed media bytes")
    expected_sha256 = hashlib.sha256(b"same seed media bytes").hexdigest()

    first = store_file(object_store, source, purpose="seed-media", addressed=True)
    second = store_file(object_store, source, purpose="seed-media", addressed=True)

    assert len(object_store.put_calls) == 1
    assert len(object_store.exists_calls) == 2
    assert second.ref.uri == first.ref.uri
    assert second.sha256 == expected_sha256
    assert second.size_bytes == len(b"same seed media bytes")


def test_store_file_addressed_puts_when_object_is_missing(tmp_path):
    object_store = CountingObjectStore()
    source = tmp_path / "seed.mp4"
    source.write_bytes(b"new seed media bytes")

    stored = store_file(object_store, source, purpose="seed-media", addressed=True)

    assert len(object_store.exists_calls) == 1
    assert object_store.put_calls == [stored.ref]
    assert stored.sha256 == hashlib.sha256(b"new seed media bytes").hexdigest()
    assert stored.size_bytes == len(b"new seed media bytes")


def test_store_file_unaddressed_puts_every_time(tmp_path):
    object_store = CountingObjectStore()
    source = tmp_path / "rendered.mp4"
    source.write_bytes(b"rendered bytes")

    first = store_file(object_store, source, purpose="generated-video")
    second = store_file(object_store, source, purpose="generated-video")

    assert len(object_store.put_calls) == 2
    assert object_store.exists_calls == []
    assert second.ref.uri != first.ref.uri


def test_store_file_forwards_tier_to_prepare_upload(tmp_path):
    object_store = RecordingObjectStore()
    source = tmp_path / "rendered.mp4"
    source.write_bytes(b"rendered bytes")

    stored = store_file(object_store, source, purpose="generated-video", tier="ephemeral")

    assert object_store.prepare_calls == [
        ("rendered.mp4", "generated-video", None, "ephemeral")
    ]
    assert stored.ref.bucket == "cutagent-ephemeral"
