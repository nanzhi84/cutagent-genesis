"""Migrate the real (legacy macmini) system prompts into the genesis prompt registry.

Reads the 16-key dump at ``tmp/prompts/macmini_system_prompts.json`` and, for each
key, ensures the matching ``prompt_*`` template exists, writes the real content as a
``published`` prompt version (covering update: reuse the canonical version id), and
creates/updates the binding to the node the runtime resolves against:

  - script keys  (hard_ad_* / ip_persona_*) -> node ``CaseAgentScriptGenerate.{persona}.{operation}``
  - broll VL keys (analysis/portrait/scenery) -> node ``MediaAssetAnnotation.broll.{flavor}``
  - cover keys   (ai_cover_prompt / ai_cover_reference_style) -> cover nodes

Default is a DRY-RUN that prints the plan only; ``--apply`` commits to the database.
The migration is idempotent: re-running it converges to the same templates, published
versions, and bindings. Template ``variables_schema_ref`` / ``output_schema_ref`` are
taken from the existing same-family seed in ``prompt_group_defaults.json`` so migrated
templates keep the schema contracts their node/UI already expect.

This script never touches the object store.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.core.contracts import PromptSchemaRef  # noqa: E402
from packages.core.storage.prompt_groups import prompt_group_seeds  # noqa: E402

DEFAULT_PROMPTS_PATH = Path(
    "/home/nanzhi/.claude/jobs/f3772e30/tmp/prompts/macmini_system_prompts.json"
)

# Operation key-suffix -> the canonical operation token used in the variant node id
# (CaseAgentScriptGenerate.{persona}.{operation}). The template/version ids keep the
# original key suffix (fresh_generate, remix_generate, ...), matching the seeds.
_SCRIPT_OPERATION_BY_SUFFIX: dict[str, str] = {
    "polish": "polish",
    "fresh_generate": "fresh",
    "remix_generate": "remix",
    "clone_generate": "clone",
    "generate": "generate",
    "semantic": "semantic",
}

_SCRIPT_PERSONAS = ("hard_ad", "ip_persona")

# B-roll VL flavor (key suffix after ``broll_vl_``) -> annotation node suffix.
_BROLL_FLAVORS = ("analysis", "portrait", "scenery")

# Cover keys -> their cover node id (purpose-derived: prompt.cover.{flavor}).
_COVER_NODE_BY_KEY: dict[str, str] = {
    "ai_cover_prompt": "PublishCover.ai_cover",
    "ai_cover_reference_style": "PublishCover.reference_style",
}

_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class TemplateMeta:
    """Schema refs + friendly name/purpose for a target template.

    When the template already has a default seed we inherit its ids/schema refs; for
    the two seed-less ``*_generate`` script families we fall back to the sibling
    ``*_fresh_generate`` family's schema refs ("沿用现有同类模板的").
    """

    template_id: str
    version_id: str
    name: str
    purpose: str
    variables_schema_id: str
    output_schema_id: str


@dataclass
class PlanItem:
    source_key: str
    template_id: str
    version_id: str
    node_id: str
    template_action: str = "noop"  # create | update | noop
    version_action: str = "noop"  # publish-new | republish | content-update
    binding_action: str = "noop"  # create | update | noop
    binding_id: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Target-state derivation (pure, DB-independent).
# ---------------------------------------------------------------------------


def _seed_index() -> dict[str, object]:
    return {seed.source_key: seed for seed in prompt_group_seeds()}


def _template_meta_for_script(seeds: dict[str, object], persona: str, suffix: str) -> TemplateMeta:
    source_key = f"{persona}_{suffix}"
    seed = seeds.get(source_key)
    if seed is not None:
        return TemplateMeta(
            template_id=seed.template_id,
            version_id=seed.version_id,
            name=seed.name,
            purpose=seed.purpose,
            variables_schema_id=seed.variables_schema_id,
            output_schema_id=seed.output_schema_id,
        )
    # Seed-less family (hard_ad_generate / ip_persona_generate): build a friendly
    # template and inherit schema refs from the sibling *_fresh_generate seed.
    sibling = seeds.get(f"{persona}_fresh_generate")
    template_id = f"prompt_script_{persona}_{suffix}"
    variables_schema_id = (
        sibling.variables_schema_id if sibling is not None else f"prompt.script.{persona}.{suffix}.variables"
    )
    output_schema_id = sibling.output_schema_id if sibling is not None else "prompt.script.output"
    persona_label = "Hard Ad" if persona == "hard_ad" else "IP Persona"
    suffix_label = suffix.replace("_", " ").title()
    return TemplateMeta(
        template_id=template_id,
        version_id=f"{template_id}_v1",
        name=f"Script Workbench {persona_label} {suffix_label}",
        purpose=f"prompt.script.{persona}.{suffix}",
        variables_schema_id=variables_schema_id,
        output_schema_id=output_schema_id,
    )


def _template_meta_for_source(seeds: dict[str, object], source_key: str) -> TemplateMeta:
    seed = seeds.get(source_key)
    if seed is None:
        raise KeyError(f"No default seed for source key {source_key!r}; cannot infer schema refs.")
    return TemplateMeta(
        template_id=seed.template_id,
        version_id=seed.version_id,
        name=seed.name,
        purpose=seed.purpose,
        variables_schema_id=seed.variables_schema_id,
        output_schema_id=seed.output_schema_id,
    )


@dataclass(frozen=True)
class Target:
    source_key: str
    meta: TemplateMeta
    node_id: str


def build_targets(seeds: dict[str, object], prompts: dict[str, str]) -> list[Target]:
    """Map each available prompt key to its template meta + runtime node id."""
    targets: list[Target] = []
    # Script variants.
    for persona in _SCRIPT_PERSONAS:
        for suffix, operation in _SCRIPT_OPERATION_BY_SUFFIX.items():
            source_key = f"{persona}_{suffix}"
            if source_key not in prompts:
                continue
            meta = _template_meta_for_script(seeds, persona, suffix)
            node_id = f"CaseAgentScriptGenerate.{persona}.{operation}"
            targets.append(Target(source_key=source_key, meta=meta, node_id=node_id))
    # B-roll VL flavors.
    for flavor in _BROLL_FLAVORS:
        source_key = f"broll_vl_{flavor}"
        if source_key not in prompts:
            continue
        meta = _template_meta_for_source(seeds, source_key)
        node_id = f"MediaAssetAnnotation.broll.{flavor}"
        targets.append(Target(source_key=source_key, meta=meta, node_id=node_id))
    # Cover keys.
    for source_key, node_id in _COVER_NODE_BY_KEY.items():
        if source_key not in prompts:
            continue
        meta = _template_meta_for_source(seeds, source_key)
        targets.append(Target(source_key=source_key, meta=meta, node_id=node_id))
    return targets


def _binding_id(node_id: str) -> str:
    # Deterministic so re-runs converge on the same binding row (idempotent upsert).
    slug = node_id.replace(".", "_")
    return f"prompt_binding_real_{slug}"


# ---------------------------------------------------------------------------
# DB-backed plan + apply.
# ---------------------------------------------------------------------------


def _load_prompts(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object of prompts at {path}, got {type(payload).__name__}.")
    return {str(k): str(v) for k, v in payload.items()}


def _open_session_factory():
    """Return a SQLAlchemy session factory, or ``None`` if the DB is unreachable.

    Dry-run tolerates an unreachable DB (it prints the full plan as create/publish).
    ``--apply`` requires a live DB and re-raises any connection error.
    """
    from packages.core.storage.database import create_database_engine, create_session_factory

    engine = create_database_engine()
    return create_session_factory(engine)


def _plan(targets: list[Target], prompts: dict[str, str], session_factory) -> list[PlanItem]:
    from packages.core.storage.database import (
        PromptBindingRow,
        PromptTemplateRow,
        PromptVersionRow,
    )

    items: list[PlanItem] = []
    db_state = None
    if session_factory is not None:
        db_state = {"templates": {}, "versions": {}, "bindings": {}}
        with session_factory() as session:
            for row in session.query(PromptTemplateRow).all():
                db_state["templates"][row.id] = row
            for row in session.query(PromptVersionRow).all():
                db_state["versions"][row.id] = (row.prompt_template_id, row.status, row.content)
            for row in session.query(PromptBindingRow).all():
                db_state["bindings"][row.id] = (
                    row.prompt_template_id,
                    row.prompt_version_id,
                    row.node_id,
                    row.case_id,
                    row.enabled,
                    row.priority,
                )

    for target in targets:
        meta = target.meta
        content = prompts[target.source_key]
        binding_id = _binding_id(target.node_id)
        item = PlanItem(
            source_key=target.source_key,
            template_id=meta.template_id,
            version_id=meta.version_id,
            node_id=target.node_id,
            binding_id=binding_id,
        )
        if db_state is None:
            item.template_action = "create-or-update"
            item.version_action = "publish"
            item.binding_action = "create-or-update"
            item.notes.append("db-unreachable: actions shown as upsert (dry-run only)")
            items.append(item)
            continue

        # Template.
        existing_tpl = db_state["templates"].get(meta.template_id)
        item.template_action = "noop" if existing_tpl is not None else "create"
        # Version (covering: reuse canonical version id, ensure published + content).
        existing_ver = db_state["versions"].get(meta.version_id)
        if existing_ver is None:
            item.version_action = "publish-new"
        else:
            _tpl_id, status, cur_content = existing_ver
            if cur_content != content and status != "published":
                item.version_action = "content-update+republish"
            elif cur_content != content:
                item.version_action = "content-update"
            elif status != "published":
                item.version_action = "republish"
            else:
                item.version_action = "noop"
        # Binding.
        existing_bind = db_state["bindings"].get(binding_id)
        desired_bind = (meta.template_id, meta.version_id, target.node_id, None, True, 1)
        if existing_bind is None:
            item.binding_action = "create"
        elif existing_bind != desired_bind:
            item.binding_action = "update"
        else:
            item.binding_action = "noop"
        items.append(item)
    return items


def _apply(targets: list[Target], prompts: dict[str, str], session_factory) -> list[PlanItem]:
    from packages.core.contracts import utcnow
    from packages.core.storage.database import (
        PromptBindingRow,
        PromptTemplateRow,
        PromptVersionRow,
    )

    applied: list[PlanItem] = []
    with session_factory() as session:
        for target in targets:
            meta = target.meta
            content = prompts[target.source_key]
            binding_id = _binding_id(target.node_id)
            now = utcnow()
            item = PlanItem(
                source_key=target.source_key,
                template_id=meta.template_id,
                version_id=meta.version_id,
                node_id=target.node_id,
                binding_id=binding_id,
            )

            # Template upsert.
            tpl = session.get(PromptTemplateRow, meta.template_id)
            if tpl is None:
                tpl = PromptTemplateRow(
                    id=meta.template_id,
                    name=meta.name,
                    purpose=meta.purpose,
                    variables_schema_ref=PromptSchemaRef(
                        schema_id=meta.variables_schema_id
                    ).model_dump(mode="json"),
                    output_schema_ref=PromptSchemaRef(
                        schema_id=meta.output_schema_id
                    ).model_dump(mode="json"),
                    status="active",
                    schema_version=_SCHEMA_VERSION,
                    created_at=now,
                    updated_at=now,
                )
                session.add(tpl)
                item.template_action = "create"
            else:
                if tpl.status != "active":
                    tpl.status = "active"
                    tpl.updated_at = now
                item.template_action = "noop"

            # Version covering-upsert -> ensure published + real content.
            ver = session.get(PromptVersionRow, meta.version_id)
            if ver is None:
                ver = PromptVersionRow(
                    id=meta.version_id,
                    prompt_template_id=meta.template_id,
                    content=content,
                    status="published",
                    changelog="Migrated real macmini system prompt.",
                    approved_at=now,
                    published_at=now,
                    schema_version=_SCHEMA_VERSION,
                    created_at=now,
                    updated_at=now,
                )
                session.add(ver)
                item.version_action = "publish-new"
            else:
                changed = False
                if ver.content != content:
                    ver.content = content
                    ver.changelog = "Migrated real macmini system prompt."
                    changed = True
                if ver.status != "published":
                    ver.status = "published"
                    ver.published_at = now
                    if ver.approved_at is None:
                        ver.approved_at = now
                    changed = True
                if changed:
                    ver.updated_at = now
                    item.version_action = "updated"
                else:
                    item.version_action = "noop"

            # Binding upsert -> node, template, version, case=None, enabled, priority=1.
            bind = session.get(PromptBindingRow, binding_id)
            if bind is None:
                bind = PromptBindingRow(
                    id=binding_id,
                    prompt_template_id=meta.template_id,
                    prompt_version_id=meta.version_id,
                    case_id=None,
                    node_id=target.node_id,
                    provider_profile_id=None,
                    priority=1,
                    enabled=True,
                    schema_version=_SCHEMA_VERSION,
                    created_at=now,
                    updated_at=now,
                )
                session.add(bind)
                item.binding_action = "create"
            else:
                changed = False
                for attr, value in (
                    ("prompt_template_id", meta.template_id),
                    ("prompt_version_id", meta.version_id),
                    ("node_id", target.node_id),
                    ("case_id", None),
                    ("enabled", True),
                    ("priority", 1),
                ):
                    if getattr(bind, attr) != value:
                        setattr(bind, attr, value)
                        changed = True
                if changed:
                    bind.updated_at = now
                    item.binding_action = "update"
                else:
                    item.binding_action = "noop"

            applied.append(item)
        session.commit()
    return applied


# ---------------------------------------------------------------------------
# Reporting.
# ---------------------------------------------------------------------------


def _print_plan(items: list[PlanItem], *, applied: bool) -> None:
    header = "APPLIED" if applied else "DRY-RUN PLAN"
    print(f"=== migrate_real_prompts: {header} ({len(items)} prompt key(s)) ===")
    for item in items:
        print(f"[{item.source_key}]")
        print(f"  template : {item.template_id}  ({item.template_action})")
        print(f"  version  : {item.version_id}  ({item.version_action}, published)")
        print(f"  binding  : {item.binding_id} -> node={item.node_id}  ({item.binding_action})")
        for note in item.notes:
            print(f"  note     : {note}")
    if not applied:
        print("--- dry-run only; re-run with --apply to commit. ---")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate real macmini system prompts into the genesis registry.")
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help="Path to macmini_system_prompts.json (16 keys).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan only (default).")
    parser.add_argument("--apply", action="store_true", help="Commit templates/versions/bindings to the database.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompts = _load_prompts(args.prompts)
    seeds = _seed_index()
    targets = build_targets(seeds, prompts)

    missing_keys = sorted(set(prompts) - {t.source_key for t in targets})
    if missing_keys:
        print(f"note: {len(missing_keys)} prompt key(s) not mapped to a node: {', '.join(missing_keys)}")

    if args.apply:
        session_factory = _open_session_factory()
        items = _apply(targets, prompts, session_factory)
        _print_plan(items, applied=True)
        return 0

    # Dry-run: read current DB state if reachable; otherwise plan as upsert.
    session_factory = None
    try:
        session_factory = _open_session_factory()
        # Force a connection probe so an unreachable DB degrades gracefully.
        with session_factory() as session:
            session.connection()
    except Exception as exc:  # noqa: BLE001 - dry-run must never hard-fail on DB.
        print(f"note: database not reachable ({type(exc).__name__}: {exc}); planning as upsert.")
        session_factory = None
    items = _plan(targets, prompts, session_factory)
    _print_plan(items, applied=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
