from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


def object_store_from_env(*, client_factory: Callable[..., Any] | None = None):
    from packages.core.storage.tiered_object_store import TieredObjectStore

    durable = _durable_store_from_env(client_factory=client_factory)
    if os.getenv("CUTAGENT_OBJECTSTORE_TIERED", "1") == "0":
        return durable
    ephemeral = _ephemeral_store_from_env(client_factory=client_factory)
    return TieredObjectStore(durable=durable, ephemeral=ephemeral)


def _durable_store_from_env(*, client_factory: Callable[..., Any] | None):
    from packages.core.storage.object_store import LocalObjectStore, S3ObjectStore

    backend = os.getenv("CUTAGENT_OBJECTSTORE_BACKEND", "local").lower()
    bucket = os.getenv("CUTAGENT_OBJECTSTORE_BUCKET", "cutagent-local")
    if backend == "local":
        return LocalObjectStore(
            root=Path(os.getenv("CUTAGENT_LOCAL_OBJECTSTORE_PATH", ".data/objectstore")),
            bucket=bucket,
        )
    if backend == "s3":
        return S3ObjectStore(
            endpoint_url=os.getenv("CUTAGENT_OBJECTSTORE_ENDPOINT", "http://127.0.0.1:9000"),
            bucket=bucket,
            access_key=os.getenv("CUTAGENT_OBJECTSTORE_ACCESS_KEY", ""),
            secret_key=os.getenv("CUTAGENT_OBJECTSTORE_SECRET_KEY", ""),
            region_name=os.getenv("CUTAGENT_OBJECTSTORE_REGION", "us-east-1"),
            addressing_style=os.getenv("CUTAGENT_OBJECTSTORE_ADDRESSING_STYLE", "path"),
            client_factory=client_factory,
            multipart_threshold_mb=int(os.getenv("CUTAGENT_OBJECTSTORE_MULTIPART_THRESHOLD_MB", "8")),
            multipart_chunk_mb=int(os.getenv("CUTAGENT_OBJECTSTORE_MULTIPART_CHUNK_MB", "8")),
            max_concurrency=int(os.getenv("CUTAGENT_OBJECTSTORE_MAX_CONCURRENCY", "4")),
            connect_timeout=int(os.getenv("CUTAGENT_OBJECTSTORE_CONNECT_TIMEOUT", "10")),
            read_timeout=int(os.getenv("CUTAGENT_OBJECTSTORE_READ_TIMEOUT", "120")),
            max_attempts=int(os.getenv("CUTAGENT_OBJECTSTORE_MAX_ATTEMPTS", "5")),
        )
    raise ValueError(f"Unsupported object store backend: {backend}")


def _ephemeral_store_from_env(*, client_factory: Callable[..., Any] | None):
    from packages.core.storage.object_store import LocalObjectStore, S3ObjectStore

    backend = os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_BACKEND", "local").lower()
    if backend == "local":
        # Fail fast under Temporal: a node-local ephemeral tier is invisible to
        # activities running on other workers, causing silent mid-pipeline
        # failures. The operator must point the ephemeral tier at shared
        # MinIO/S3. Local runtime keeps the local default.
        if os.getenv("CUTAGENT_WORKFLOW_RUNTIME", "local").lower() == "temporal":
            raise RuntimeError(
                "Invalid ObjectStore configuration: ephemeral tier resolves to a "
                "node-local 'local' backend while CUTAGENT_WORKFLOW_RUNTIME=temporal. "
                "Under multi-worker Temporal, ephemeral artifacts written by one "
                "worker are unreadable by activities on another worker, causing "
                "silent mid-pipeline failures. Point the ephemeral tier at shared "
                "MinIO/S3: set CUTAGENT_EPHEMERAL_OBJECTSTORE_BACKEND=s3 (and the "
                "related CUTAGENT_EPHEMERAL_OBJECTSTORE_* endpoint/bucket/credential "
                "variables)."
            )
        root = Path(
            os.getenv(
                "CUTAGENT_OBJECTSTORE_EPHEMERAL_PATH",
                str(Path(tempfile.gettempdir()) / "cutagent-ephemeral"),
            )
        )
        return LocalObjectStore(root=root, bucket="cutagent-ephemeral")
    if backend == "s3":
        return S3ObjectStore(
            endpoint_url=os.getenv(
                "CUTAGENT_EPHEMERAL_OBJECTSTORE_ENDPOINT",
                "http://127.0.0.1:9000",
            ),
            bucket=os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_BUCKET", "cutagent-ephemeral"),
            access_key=os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_ACCESS_KEY", ""),
            secret_key=os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_SECRET_KEY", ""),
            region_name=os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_REGION", "us-east-1"),
            addressing_style=os.getenv("CUTAGENT_EPHEMERAL_OBJECTSTORE_ADDRESSING_STYLE", "path"),
            client_factory=client_factory,
        )
    raise ValueError(f"Unsupported ephemeral object store backend: {backend}")
