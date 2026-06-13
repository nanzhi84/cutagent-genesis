from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from packages.core.contracts._common import (
    ArtifactRef,
    BaseListQuery,
    ContractModel,
    DegradationCode,
    DegradationNotice,
    EntityMeta,
    JobStatus,
    JobType,
    NodeError,
    NodeStatus,
    RunStatus,
    UploadKind,
    UploadStatus,
    UserRole,
    WarningCode,
    utcnow,
)
from packages.core.contracts._media import MediaAssetRecord
from packages.core.contracts._publishing import PublishPackage


class VoiceOptions(ContractModel):
    voice_id: str
    provider_profile_id: str | None = None
    speed: float = Field(1.0, ge=0.5, le=2.0)
    emotion: str = "neutral"
    volume: float = Field(1.0, ge=0.0, le=2.0)


class PortraitOptions(ContractModel):
    template_mode: Literal["agent", "specific", "sequence"] = "agent"
    specific_template_id: str | None = None
    template_sequence_ids: list[str] = Field(default_factory=list)
    rhythm_preset: Literal["steady", "balanced", "fast"] = "balanced"


class BrollOptions(ContractModel):
    enabled: bool = True
    case_id: str | None = None
    max_inserts: int = Field(4, ge=0, le=20)
    min_segment_duration: float = Field(3.0, ge=0.5)


class LipSyncOptions(ContractModel):
    enabled: bool = True
    provider_profile_id: str = "runninghub.heygem.default"
    ref_image_artifact_id: str | None = None
    video_extension: bool = False
    query_face_threshold: float | None = Field(None, ge=0.0, le=1.0)
    timeout_minutes: int = Field(30, ge=5, le=120)


class SubtitleOptions(ContractModel):
    enabled: bool = True
    style_preset: str = "douyin"
    font_id: str | None = None
    font_size: int | None = None
    position: dict[str, float] | None = None


class BgmOptions(ContractModel):
    enabled: bool = True
    bgm_id: str | None = None
    volume: float = Field(0.25, ge=0, le=1)
    auto_mix: bool = True


class CoverOptions(ContractModel):
    mode: Literal["none", "frame", "ai"] = "frame"
    template_id: str | None = None


class OutputOptions(ContractModel):
    export_jianying_draft: bool = True
    export_editor_handoff: bool = True
    upload_to_oss: bool = True
    keep_local_originals: bool = False
    width: int = 1080
    height: int = 1920
    fps: int = 30
    format: Literal["mp4"] = "mp4"


class StrictnessOptions(ContractModel):
    strict_timestamps: bool = True
    portrait_insufficient_policy: Literal["hard_fail"] = "hard_fail"
    broll_insufficient_policy: Literal["soft_degrade"] = "soft_degrade"
    bgm_unavailable_policy: Literal["soft_degrade"] = "soft_degrade"
    strict_cost_pricing: bool = False


class DigitalHumanVideoRequest(ContractModel):
    schema_version: Literal["digital_human_video_request.v1"] = "digital_human_video_request.v1"
    case_id: str
    script: str
    title: str | None = None
    publish_content: str = ""
    script_version_id: str | None = None
    creative_intent_ref: ArtifactRef | None = None
    workflow_template_id: str = "digital_human_v2"
    voice: VoiceOptions = Field(default_factory=VoiceOptions)
    portrait: PortraitOptions = Field(default_factory=PortraitOptions)
    broll: BrollOptions = Field(default_factory=BrollOptions)
    lipsync: LipSyncOptions = Field(default_factory=LipSyncOptions)
    subtitle: SubtitleOptions = Field(default_factory=SubtitleOptions)
    bgm: BgmOptions = Field(default_factory=BgmOptions)
    cover: CoverOptions = Field(default_factory=CoverOptions)
    output: OutputOptions = Field(default_factory=OutputOptions)
    strictness: StrictnessOptions = Field(default_factory=StrictnessOptions)


class CaseAgentRunRequest(ContractModel):
    schema_version: Literal["case_agent_run_request.v1"] = "case_agent_run_request.v1"
    case_id: str
    goal: Literal["brief", "script_draft", "memory_proposal"]
    source_binding_ids: list[str] = Field(default_factory=list)


class PublishBatchRequest(ContractModel):
    schema_version: Literal["publish_batch_request.v1"] = "publish_batch_request.v1"
    publish_package_ids: list[str]
    platform_targets: list[str]


class AnnotationBatchRequest(ContractModel):
    schema_version: Literal["annotation_batch_request.v1"] = "annotation_batch_request.v1"
    asset_ids: list[str]
    provider_profile_id: str | None = None


JobRequest = Annotated[
    DigitalHumanVideoRequest | CaseAgentRunRequest | PublishBatchRequest | AnnotationBatchRequest,
    Field(discriminator="schema_version"),
]


class Job(EntityMeta):
    type: JobType
    status: JobStatus = JobStatus.draft
    case_id: str | None = None
    created_by: str | None = None
    request_schema: str
    request: JobRequest
    active_run_id: str | None = None
    latest_finished_video_id: str | None = None


class WorkflowRun(EntityMeta):
    job_id: str
    case_id: str | None = None
    workflow_template_id: str
    workflow_version: str
    status: RunStatus = RunStatus.created
    requested_by: str | None = None
    run_attempt: int = 1
    resume_from_run_id: str | None = None
    retry_of_run_id: str | None = None
    experiment_assignment_id: str | None = None
    public_report_artifact_id: str | None = None
    debug_report_artifact_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class NodeRun(EntityMeta):
    run_id: str
    node_id: str
    node_version: str
    status: NodeStatus
    attempt: int = 1
    input_manifest_hash: str
    output_artifact_ids: list[str] = Field(default_factory=list)
    provider_invocation_ids: list[str] = Field(default_factory=list)
    error: NodeError | None = None
    skipped_reason: str | None = None
    degradation_reason: str | None = None
    warnings: list[WarningCode] = Field(default_factory=list)
    degradations: list[DegradationNotice] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ValidatedProductionSpec(ContractModel):
    request: DigitalHumanVideoRequest
    workflow_template_id: str
    workflow_version: str
    compatible: bool = True


class AuthUser(EntityMeta):
    email: str
    display_name: str
    role: UserRole = UserRole.viewer
    status: Literal["active", "disabled"] = "active"


class SessionInfo(ContractModel):
    user: AuthUser
    session_id: str
    expires_at: datetime
    request_id: str


class LoginRequest(ContractModel):
    identifier: str | None = None
    email: str | None = None
    password: str

    @model_validator(mode="after")
    def require_identifier(self) -> "LoginRequest":
        if not (self.identifier or self.email):
            raise ValueError("identifier or email is required")
        return self


class RegisterRequest(ContractModel):
    email: str
    password: str
    display_name: str
    registration_code: str | None = None


class AuthResponse(ContractModel):
    user: AuthUser
    session: SessionInfo
    request_id: str


class ChangePasswordRequest(ContractModel):
    old_password: str
    new_password: str = Field(min_length=8)


class UserListQuery(BaseListQuery):
    role: UserRole | None = None
    status: Literal["active", "disabled"] | None = None


class AdminCreateUserRequest(ContractModel):
    email: str
    display_name: str
    role: UserRole = UserRole.viewer
    password: str | None = None


class AdminUpdateUserRequest(ContractModel):
    display_name: str | None = None
    role: UserRole | None = None
    status: Literal["active", "disabled"] | None = None


class RegistrationCodeQuery(BaseListQuery):
    status: Literal["active", "disabled", "expired"] | None = None


class RegistrationCodePreview(ContractModel):
    id: str
    role: UserRole
    status: Literal["active", "disabled", "expired"]
    max_uses: int | None = None
    used_count: int
    purpose: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class CreatedRegistrationCode(RegistrationCodePreview):
    plaintext_code: str


class CreateRegistrationCodeRequest(ContractModel):
    role: UserRole
    custom_code: str | None = None
    purpose: str | None = None
    max_uses: int | None = None
    expires_at: datetime | None = None


class UpdateRegistrationCodeRequest(ContractModel):
    status: Literal["active", "disabled", "expired"] | None = None
    purpose: str | None = None
    expires_at: datetime | None = None


class UpdateMeRequest(ContractModel):
    display_name: str | None = None


class PrepareUploadRequest(ContractModel):
    kind: UploadKind
    case_id: str | None = None
    filename: str
    content_type: str
    size_bytes: int = Field(gt=0)
    sha256: str | None = None
    multipart: bool = False
    stabilize: bool = False


class UploadSession(EntityMeta):
    kind: UploadKind
    case_id: str | None = None
    filename: str
    content_type: str
    size_bytes: int
    sha256: str | None = None
    status: UploadStatus = UploadStatus.prepared
    upload_url: str | None = None
    local_temp_path: str | None = None
    object_uri: str | None = None
    stabilize: bool = False
    stabilized: bool = False
    expires_at: datetime = Field(default_factory=lambda: utcnow() + timedelta(hours=1))


class CompleteUploadRequest(ContractModel):
    upload_session_id: str
    size_bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class CompleteUploadResponse(ContractModel):
    upload_session: UploadSession
    artifact: ArtifactRef
    media_asset: MediaAssetRecord | None = None
    publish_package: PublishPackage | None = None
    request_id: str


class SecretQuery(BaseListQuery):
    provider_id: str | None = None
    environment: str | None = None
    status: str | None = None


class CreateSecretRequest(ContractModel):
    provider_id: str
    environment: Literal["local", "dev", "staging", "prod"]
    name: str
    plaintext_secret: str


class RotateSecretRequest(ContractModel):
    plaintext_secret: str
    reason: str


class DisableSecretRequest(ContractModel):
    reason: str


class SecretStatus(str, Enum):
    active = "active"
    disabled = "disabled"
    rotated = "rotated"


class SecretRecord(EntityMeta):
    provider_id: str
    environment: Literal["local", "dev", "staging", "prod"]
    name: str
    secret_ref: str
    status: SecretStatus = SecretStatus.active
    rotated_from_secret_id: str | None = None
    rotated_at: datetime | None = None
    disabled_at: datetime | None = None


class SecretPreview(EntityMeta):
    provider_id: str
    environment: str
    name: str
    secret_ref: str | None = None
    status: SecretStatus = SecretStatus.active
    rotated_from_secret_id: str | None = None
    rotated_at: datetime | None = None
    disabled_at: datetime | None = None
    masked_value: str = "********"


class CaseListQuery(BaseListQuery):
    search: str | None = None
    owner_user_id: str | None = None


class CreateCaseRequest(ContractModel):
    name: str
    description: str | None = None
    industry: str | None = None
    product: str | None = None
    target_audience: str | None = None


class PatchCaseRequest(ContractModel):
    name: str | None = None
    description: str | None = None
    product: str | None = None
    target_audience: str | None = None
    status: Literal["active", "archived"] | None = None


class DeleteCaseRequest(ContractModel):
    reason: str | None = None


class CaseListItem(EntityMeta):
    name: str
    owner_user_id: str | None = None
    active_memory_count: int = 0
    status: Literal["active", "archived"] = "active"


class CaseDetail(CaseListItem):
    description: str | None = None
    industry: str | None = None
    product: str | None = None
    target_audience: str | None = None


CreateDigitalHumanVideoJobRequest = DigitalHumanVideoRequest


class CreateRunRequest(ContractModel):
    mode: Literal["new", "retry", "resume"] = "new"
    reason: str | None = None


class CancelRunRequest(ContractModel):
    reason: str | None = None
    force: bool = False


class RetryRunRequest(ContractModel):
    reason: str | None = None


class ResumeRunRequest(ContractModel):
    reason: str | None = None
    reuse_valid_artifacts: bool = True


class WorkflowRunResponse(ContractModel):
    run: WorkflowRun
    request_id: str


RetryRunResponse = WorkflowRunResponse


ResumeRunResponse = WorkflowRunResponse


class CreateJobResponse(ContractModel):
    job: Job
    initial_run: WorkflowRun | None
    request_id: str


class JobDetailResponse(ContractModel):
    job: Job
    runs: list[WorkflowRun]
    latest_report_artifact_id: str | None = None
    request_id: str = "req_local"


class RunDetailResponse(ContractModel):
    run: WorkflowRun
    node_runs: list[NodeRun]
    artifacts: list[ArtifactRef]
    artifact_payloads: dict[str, JsonValue] = Field(default_factory=dict)
    request_id: str = "req_local"


class RunCard(ContractModel):
    run_id: str = Field(alias="runId")
    job_id: str = Field(alias="jobId")
    case_id: str = Field(alias="caseId")
    status: RunStatus
    progress: float = Field(ge=0, le=1)
    current_node_label: str | None = Field(default=None, alias="currentNodeLabel")
    title: str
    preview_url: str | None = Field(default=None, alias="previewUrl")
    warnings: list[str] = Field(default_factory=list)
    can_resume: bool = Field(alias="canResume")
    can_retry: bool = Field(alias="canRetry")
    can_publish: bool = Field(alias="canPublish")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class RunActionResponse(ContractModel):
    run: WorkflowRun
    accepted: bool
    request_id: str = "req_local"


class RunPublicReportArtifact(ContractModel):
    run_id: str
    status: RunStatus
    summary: str
    node_statuses: dict[str, NodeStatus]
    warnings: list[WarningCode] = Field(default_factory=list)
    degradations: list[DegradationCode] = Field(default_factory=list)


class RunDebugReportArtifact(RunPublicReportArtifact):
    artifact_ids: list[str] = Field(default_factory=list)
    provider_invocation_ids: list[str] = Field(default_factory=list)
    node_errors: list[NodeError] = Field(default_factory=list)


class RunReportResponse(ContractModel):
    public_report: RunPublicReportArtifact
    debug_report: RunDebugReportArtifact | None = None
    request_id: str = "req_local"


class RunArtifactsResponse(ContractModel):
    run_id: str
    artifacts: list[ArtifactRef]
    request_id: str


class RunEventsQuery(BaseListQuery):
    since_id: str | None = None
