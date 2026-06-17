from __future__ import annotations

from packages.core.contracts import CaseMemory, CaseMemoryScope, ScriptDraft, ScriptVersion, VideoVersion
from packages.core.storage.database import CaseMemoryRow, ScriptDraftRow, ScriptVersionRow, VideoVersionRow


def script_draft_row_to_contract(row: ScriptDraftRow) -> ScriptDraft:
    return ScriptDraft(
        id=row.id,
        case_id=row.case_id,
        title=row.title,
        script=row.script,
        status=row.status,
        memory_ids=list(row.memory_ids or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
    )


def script_version_row_to_contract(row: ScriptVersionRow) -> ScriptVersion:
    return ScriptVersion(
        id=row.id,
        case_id=row.case_id,
        title=row.title,
        script=row.script,
        creative_intent_artifact_id=row.creative_intent_artifact_id,
        adopted_from_draft_id=row.adopted_from_draft_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
    )


def case_memory_row_to_contract(row: CaseMemoryRow) -> CaseMemory:
    parsed = CaseMemoryScope.model_validate(row.scope or {})
    scope = parsed.model_copy(
        update={
            "scope_key": parsed.scope_key or row.scope_key,
            "valid_from": parsed.valid_from or row.valid_from,
            "valid_until": parsed.valid_until or row.valid_until,
        }
    )
    return CaseMemory(
        id=row.id,
        case_id=row.case_id,
        status=row.status,  # type: ignore[arg-type]
        memory_type=row.memory_type,  # type: ignore[arg-type]
        scope=scope,
        insight=row.insight,
        evidence=list(row.evidence or []),
        confidence=row.confidence,
        sample_size=row.sample_size,
        supersedes_memory_id=row.supersedes_memory_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
    )


def video_version_row_to_contract(row: VideoVersionRow) -> VideoVersion:
    return VideoVersion(
        id=row.id,
        case_id=row.case_id,
        script_version_id=row.script_version_id,
        finished_video_id=row.finished_video_id,
        timeline_plan_artifact_id=row.timeline_plan_artifact_id,
        style_plan_artifact_id=row.style_plan_artifact_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
    )
