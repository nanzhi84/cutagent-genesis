#!/usr/bin/env python3
"""Backfill ``media_assets`` card metadata (thumbnail / dimensions / duration).

Stage-A write-only utility (run later). For every portrait / b-roll media asset
already migrated into the genesis SQL backend, this reverse-maps the asset's
source-artifact OSS uri back to its entry in the legacy indexes and back-fills:

  * ``thumbnail_uri``  — portrait: ``item.thumbnail`` rendered as
        ``s3://<bucket>/<upload_prefix><thumbnail>`` (relative thumbnail path
        under uploads/). B-roll uses ``item.thumbnail_path`` the same way; when
        absent it is left empty (the migration carries none either).
  * ``duration_sec``   — from the index entry's ``duration``.
  * ``width`` / ``height`` — from the index entry when present (the legacy
        portrait/b-roll index entries usually omit pixel dimensions, so these
        stay empty unless the index carries them).

Index source
------------
The two indexes live on the legacy Aliyun OSS bucket (not the local durable
object store). They are read with the same ``LegacyOssClient`` the migration
uses (boto3, S3-compatible). Credentials are taken from ``--api-keys``
(default ``.data/api_keys.json``) and bridged into the ``CUTAGENT_*OBJECTSTORE*``
env the client reads. ``--index-dir`` lets you point at a pre-pulled local copy
of the indexes instead (expects ``templates_pool/index.json`` and
``cases/<case_dir>/broll/library.json`` under it).

Database
--------
Connects via the standard ``create_database_engine`` / ``create_session_factory``
(SQLAlchemy backend; ``CUTAGENT_DATABASE_URL`` must be set, or rely on the
``.env``/default ``postgresql+psycopg://cutagent:cutagent@127.0.0.1:55432/cutagent``).

The script is idempotent and re-runnable: a field is only written when it is
currently empty/None on the row (or differs from the resolved value). Dry-run is
the default; ``--apply`` commits. A per-field backfill count is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_api_keys() -> Path:
    """Locate api_keys.json: prefer this checkout's ``.data``, else the main repo's.

    In a worktree under ``<repo>/.claude/worktrees/<name>`` the real
    ``.data/api_keys.json`` lives in the main checkout, so fall back up the tree.
    """
    candidates = [ROOT / ".data" / "api_keys.json"]
    for parent in ROOT.parents:
        candidates.append(parent / ".data" / "api_keys.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

from packages.migrations.legacy_asset_utils import (  # noqa: E402
    DEFAULT_BUCKET,
    DEFAULT_UPLOAD_PREFIX,
    as_list,
    optional_float,
)

# ── api_keys.json → CUTAGENT_*OBJECTSTORE* env bridge ──────────────────────────

# Maps the flat api_keys.json fields onto the env vars LegacyOssClient.from_env
# reads. The legacy bucket/endpoint are the Aliyun OSS values; we only set them
# when not already provided so an explicit env override always wins.
_API_KEY_ENV_BRIDGE = {
    "aliyun_access_key_id": ("CUTAGENT_LEGACY_OBJECTSTORE_ACCESS_KEY", "CUTAGENT_OBJECTSTORE_ACCESS_KEY"),
    "aliyun_access_key_secret": ("CUTAGENT_LEGACY_OBJECTSTORE_SECRET_KEY", "CUTAGENT_OBJECTSTORE_SECRET_KEY"),
}


def _load_api_keys(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _bridge_oss_env(api_keys: dict[str, Any]) -> None:
    for source_key, env_names in _API_KEY_ENV_BRIDGE.items():
        value = api_keys.get(source_key)
        if not value:
            continue
        for env_name in env_names:
            os.environ.setdefault(env_name, str(value))
    endpoint = api_keys.get("aliyun_oss_endpoint")
    if endpoint:
        # boto3 wants a scheme; the api_keys.json value is bare host:port-less host.
        endpoint_url = endpoint if "://" in str(endpoint) else f"https://{endpoint}"
        os.environ.setdefault("CUTAGENT_LEGACY_OBJECTSTORE_ENDPOINT", endpoint_url)
        os.environ.setdefault("CUTAGENT_OBJECTSTORE_ENDPOINT", endpoint_url)
    # OSS uses virtual-hosted-style addressing (bucket in the host).
    os.environ.setdefault("CUTAGENT_OBJECTSTORE_ADDRESSING_STYLE", "virtual")


# ── OSS key normalization (mirrors LegacyAssetMigrator._oss_key) ───────────────


def _normalize_key(path: Any, upload_prefix: str) -> str | None:
    """Normalize an index ``path`` / artifact uri into the canonical OSS key.

    Identical normalization to ``LegacyAssetMigrator._oss_key`` so the keys
    derived from the artifact uri and from the index entry collide for the same
    underlying object.
    """
    if path is None:
        return None
    text = str(path).strip().lstrip("/")
    if not text:
        return None
    if text.startswith("s3://"):
        return urlsplit(text).path.lstrip("/") or None
    if text.startswith(upload_prefix):
        return text
    while text.startswith("uploads/"):
        text = text.removeprefix("uploads/")
    return f"{upload_prefix}{text}" if text else None


# ── index loading ──────────────────────────────────────────────────────────────


class IndexSource:
    """Reads the two legacy indexes from OSS or a pre-pulled local directory."""

    def __init__(self, *, oss_client: Any | None, local_dir: Path | None, upload_prefix: str) -> None:
        self.oss = oss_client
        self.local_dir = local_dir
        self.upload_prefix = upload_prefix

    def _load_json(self, key: str) -> Any:
        # key is the full OSS key including the upload prefix.
        if self.local_dir is not None:
            rel = key.removeprefix(self.upload_prefix)
            candidate = self.local_dir / rel
            if not candidate.exists():
                return None
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        if self.oss is None:
            return None
        try:
            return self.oss.get_json(key)
        except FileNotFoundError:
            return None

    def portrait_index(self) -> Any:
        return self._load_json(f"{self.upload_prefix}templates_pool/index.json")

    def broll_library(self, case_dir: str) -> Any:
        return self._load_json(f"{self.upload_prefix}cases/{case_dir}/broll/library.json")


def _portrait_items(index: Any) -> list[dict]:
    if isinstance(index, dict):
        inner = index.get("templates")
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
        return [value for value in index.values() if isinstance(value, dict)]
    return [item for item in as_list(index) if isinstance(item, dict)]


def _broll_items(library: Any) -> list[dict]:
    values = library.get("videos") if isinstance(library, dict) else library
    return [item for item in as_list(values) if isinstance(item, dict)]


# ── field extraction from an index entry ───────────────────────────────────────


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _thumbnail_uri(item: dict, *, bucket: str, upload_prefix: str) -> str | None:
    # portrait entries carry ``thumbnail`` (relative path under uploads/), b-roll
    # entries carry ``thumbnail_path``. Both render to s3://<bucket>/<prefix><rel>.
    raw = item.get("thumbnail") or item.get("thumbnail_path")
    key = _normalize_key(raw, upload_prefix)
    if not key:
        return None
    return f"s3://{bucket}/{key}"


def _resolved_fields(item: dict, *, bucket: str, upload_prefix: str) -> dict[str, Any]:
    return {
        "thumbnail_uri": _thumbnail_uri(item, bucket=bucket, upload_prefix=upload_prefix),
        "duration_sec": optional_float(item.get("duration")),
        "width": _optional_int(item.get("width")),
        "height": _optional_int(item.get("height")),
    }


# ── backfill driver ────────────────────────────────────────────────────────────

_BACKFILL_KINDS = {"portrait", "broll"}


def _build_lookup(
    *,
    index_source: IndexSource,
    case_dirs: list[str],
    bucket: str,
    upload_prefix: str,
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """Build {normalized OSS key -> resolved field dict} from both indexes."""
    lookup: dict[str, dict[str, Any]] = {}

    portrait_index = index_source.portrait_index()
    if portrait_index is None:
        warnings.append("WARN portrait index (templates_pool/index.json) not found")
    for item in _portrait_items(portrait_index):
        if str(item.get("material_type") or "portrait").strip().lower() != "portrait":
            continue
        key = _normalize_key(item.get("path"), upload_prefix)
        if key:
            lookup.setdefault(key, _resolved_fields(item, bucket=bucket, upload_prefix=upload_prefix))

    for case_dir in case_dirs:
        library = index_source.broll_library(case_dir)
        if library is None:
            continue
        for item in _broll_items(library):
            key = _normalize_key(item.get("path"), upload_prefix)
            if key:
                lookup.setdefault(key, _resolved_fields(item, bucket=bucket, upload_prefix=upload_prefix))
    return lookup


def _case_dirs(cases_path: Path | None, warnings: list[str]) -> list[str]:
    """Reconstruct the broll case-dir names ``<name>_<id[:8]>`` (migration formula)."""
    if cases_path is None or not cases_path.exists():
        if cases_path is not None:
            warnings.append(f"WARN cases.json not found at {cases_path}; b-roll libraries skipped")
        return []
    try:
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        warnings.append(f"WARN cases.json unreadable at {cases_path}; b-roll libraries skipped")
        return []
    dirs: list[str] = []
    for case in as_list(cases):
        if not isinstance(case, dict) or not case.get("id"):
            continue
        legacy_id = str(case["id"])
        name = str(case.get("name") or case.get("case_name") or legacy_id).strip()
        dirs.append(f"{name}_{legacy_id[:8]}")
    return dirs


def _artifact_key(artifact: Any, upload_prefix: str) -> str | None:
    for candidate in (getattr(artifact, "oss_uri", None), getattr(artifact, "uri", None)):
        key = _normalize_key(candidate, upload_prefix)
        if key:
            return key
    return None


def run(
    *,
    apply: bool,
    bucket: str,
    upload_prefix: str,
    index_source: IndexSource,
    cases_path: Path | None,
    out=sys.stdout,
) -> int:
    from packages.core.storage.database import create_database_engine, create_session_factory
    from packages.core.storage.database import ArtifactRow, MediaAssetRow

    warnings: list[str] = []
    case_dirs = _case_dirs(cases_path, warnings)
    lookup = _build_lookup(
        index_source=index_source,
        case_dirs=case_dirs,
        bucket=bucket,
        upload_prefix=upload_prefix,
        warnings=warnings,
    )

    mode = "APPLY" if apply else "DRY-RUN"
    counts = {"thumbnail_uri": 0, "duration_sec": 0, "width": 0, "height": 0}
    considered = 0
    matched = 0
    unmatched: list[str] = []
    no_artifact: list[str] = []

    session_factory = create_session_factory(create_database_engine())
    with session_factory() as session:
        rows = session.query(MediaAssetRow).filter(MediaAssetRow.kind.in_(_BACKFILL_KINDS)).all()
        for row in rows:
            considered += 1
            if not row.source_artifact_id:
                no_artifact.append(f"{row.id} ({row.kind}): no source_artifact_id")
                continue
            artifact = session.get(ArtifactRow, row.source_artifact_id)
            if artifact is None:
                no_artifact.append(f"{row.id} ({row.kind}): artifact {row.source_artifact_id} missing")
                continue
            key = _artifact_key(artifact, upload_prefix)
            if not key:
                no_artifact.append(f"{row.id} ({row.kind}): artifact has no OSS uri")
                continue
            fields = lookup.get(key)
            if fields is None:
                unmatched.append(f"{row.id} ({row.kind}): no index entry for {key}")
                continue
            matched += 1
            for name, value in fields.items():
                if value in (None, ""):
                    continue
                current = getattr(row, name)
                if current == value:
                    continue
                # Idempotent: only fill empties; never clobber a non-empty value
                # that differs (the index is authoritative only for blanks).
                if current not in (None, ""):
                    continue
                counts[name] += 1
                if apply:
                    setattr(row, name, value)
        if apply:
            session.commit()

    print(f"{mode} media-field backfill", file=out)
    print(f"index entries (OSS keys): {len(lookup)}", file=out)
    print(f"assets considered (portrait+broll): {considered}", file=out)
    print(f"assets matched to an index entry: {matched}", file=out)
    for name in ("thumbnail_uri", "duration_sec", "width", "height"):
        print(f"{name} backfilled: {counts[name]}", file=out)
    print(f"assets without resolvable source artifact: {len(no_artifact)}", file=out)
    print(f"assets with no matching index entry: {len(unmatched)}", file=out)
    for message in warnings:
        print(message, file=out)
    for message in (no_artifact + unmatched)[:50]:
        print(f"  - {message}", file=out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes. Default is dry-run (plan only).")
    parser.add_argument(
        "--api-keys",
        type=Path,
        default=_default_api_keys(),
        help="api_keys.json with Aliyun OSS credentials (default: <repo>/.data/api_keys.json).",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=None,
        help="Read the legacy indexes from this pre-pulled local directory instead of OSS.",
    )
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=None,
        help="cases.json used to derive b-roll case-dir names (skips b-roll libraries if omitted).",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("CUTAGENT_LEGACY_OBJECTSTORE_BUCKET") or DEFAULT_BUCKET,
        help=f"Legacy OSS bucket (default: {DEFAULT_BUCKET}).",
    )
    parser.add_argument(
        "--upload-prefix",
        default=os.getenv("CUTAGENT_LEGACY_UPLOAD_PREFIX", DEFAULT_UPLOAD_PREFIX),
        help=f"Upload prefix (default: {DEFAULT_UPLOAD_PREFIX}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    upload_prefix = args.upload_prefix.strip("/") + "/"

    index_source: IndexSource
    if args.index_dir is not None:
        index_source = IndexSource(oss_client=None, local_dir=args.index_dir, upload_prefix=upload_prefix)
    else:
        _bridge_oss_env(_load_api_keys(args.api_keys))
        from packages.migrations.legacy_asset_clients import LegacyOssClient

        oss_client = LegacyOssClient.from_env(bucket=args.bucket)
        index_source = IndexSource(oss_client=oss_client, local_dir=None, upload_prefix=upload_prefix)

    return run(
        apply=bool(args.apply),
        bucket=args.bucket,
        upload_prefix=upload_prefix,
        index_source=index_source,
        cases_path=args.cases_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
