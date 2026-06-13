from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from packages.core.contracts._common import (
    ArtifactKind,
    ContractModel,
    EntityMeta,
    ErrorCode,
    Money,
    ProviderError,
    ProviderStatus,
    utcnow,
)


class UsageMeterRecord(EntityMeta):
    provider_invocation_id: str
    provider_id: str
    model_id: str
    capability_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    audio_seconds: float = 0
    video_seconds: float = 0
    image_count: int = 0
    provider_credits: Decimal | None = None
    raw_usage: dict[str, Any] = Field(default_factory=dict)


class ProviderInvocation(EntityMeta):
    case_id: str | None = None
    run_id: str | None = None
    node_run_id: str | None = None
    provider_id: str
    model_id: str
    provider_profile_id: str
    capability_id: str
    prompt_version_id: str | None = None
    status: ProviderStatus
    usage: UsageMeterRecord | None = None
    price_item_id: str | None = None
    billing_status: Literal["estimated", "reconciled", "unpriced", "ignored"] = "estimated"
    duration_ms: int = 0
    retry_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: Money | None = None
    actual_cost: Money | None = None
    request_artifact_id: str | None = None
    response_artifact_id: str | None = None
    external_job_id: str | None = None
    error: ProviderError | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class RetryPolicy(ContractModel):
    max_attempts: int = Field(1, ge=1, le=10)
    backoff_seconds: float = Field(0, ge=0)
    backoff_multiplier: float = Field(2.0, ge=1.0)
    retryable_error_codes: list[ErrorCode] = Field(default_factory=list)


class ResumePolicy(ContractModel):
    mode: Literal["never", "reuse_if_hash_match", "always_rerun"] = "reuse_if_hash_match"
    reusable_artifact_kinds: list[ArtifactKind] = Field(default_factory=list)
    side_effect_replay: Literal["forbidden", "idempotent_only"] = "idempotent_only"


class WorkflowEdge(ContractModel):
    from_node_id: str
    to_node_id: str
    condition: str | None = None


class NodeSpec(ContractModel):
    node_id: str
    node_version: str = "v1"
    input_schema: str
    output_artifact_kinds: list[ArtifactKind]
    output_artifact_schema_versions: dict[ArtifactKind, str] = Field(default_factory=dict)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    resume_policy: ResumePolicy = Field(default_factory=ResumePolicy)
    side_effects: list[
        Literal["provider_call", "ledger_commit", "external_upload", "publish_attempt"]
    ] = Field(default_factory=list)
    idempotency_key: str | None = None


class WorkflowTemplate(ContractModel):
    workflow_template_id: str
    version: str
    nodes: list[NodeSpec]
    edges: list[WorkflowEdge] = Field(default_factory=list)
