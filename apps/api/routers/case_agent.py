from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api.dependencies import require_role
from apps.api.services import case_agent as service
from packages.core import contracts as c

router = APIRouter()


@router.get("/api/cases/{case_id}/agent/drafts", response_model=c.PageResponse[c.ScriptDraft])
def script_drafts(request: Request, case_id: str, limit: int = 50) -> c.PageResponse[c.ScriptDraft]:
    return service.script_drafts(request, case_id, limit)


@router.post(
    "/api/cases/{case_id}/agent/drafts/{draft_id}/adopt",
    response_model=c.ScriptVersion,
    status_code=201,
)
def adopt_script_draft(
    case_id: str, draft_id: str, payload: c.AdoptScriptDraftRequest, request: Request
) -> c.ScriptVersion:
    require_role(request, c.UserRole.operator)
    return service.adopt_script_draft(case_id, draft_id, payload, request)


@router.get("/api/cases/{case_id}/performance", response_model=c.CasePerformanceResponse)
def case_performance(request: Request, case_id: str, window: str = "7d") -> c.CasePerformanceResponse:
    return service.case_performance(request, case_id, window)


@router.post("/api/cases/{case_id}/metrics/import", response_model=c.ImportBatchReport, status_code=202)
def import_metrics(case_id: str, payload: c.MetricsImportRequest, request: Request) -> c.ImportBatchReport:
    require_role(request, c.UserRole.operator)
    return service.import_metrics(case_id, payload, request)


@router.post("/api/cases/{case_id}/scripts/generate-with-memory", response_model=c.ScriptDraft, status_code=202)
def generate_script_with_memory(
    case_id: str, payload: c.GenerateScriptWithMemoryRequest, request: Request
) -> c.ScriptDraft:
    require_role(request, c.UserRole.operator)
    return service.generate_script_with_memory(case_id, payload, request)
