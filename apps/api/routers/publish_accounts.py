from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from apps.api.dependencies import require_role
from apps.api.services import publish_accounts as service
from packages.core import contracts as c

router = APIRouter()


# --- clients ---


@router.get("/api/publish/clients", response_model=c.PageResponse[c.Client])
def list_clients(
    request: Request, limit: int = 50, include_archived: bool = False
) -> c.PageResponse[c.Client]:
    require_role(request, c.UserRole.operator)
    return service.list_clients(request, limit=limit, include_archived=include_archived)


@router.post("/api/publish/clients", response_model=c.Client, status_code=201)
def create_client(payload: c.CreateClientRequest, request: Request) -> c.Client:
    require_role(request, c.UserRole.operator)
    return service.create_client(payload, request)


@router.patch("/api/publish/clients/{client_id}", response_model=c.Client)
def patch_client(
    client_id: str, payload: c.PatchClientRequest, request: Request
) -> c.Client | JSONResponse:
    require_role(request, c.UserRole.operator)
    return service.patch_client(client_id, payload, request)


@router.delete("/api/publish/clients/{client_id}", response_model=c.OkResponse)
def delete_client(client_id: str, request: Request) -> c.OkResponse | JSONResponse:
    require_role(request, c.UserRole.operator)
    return service.delete_client(client_id, request)


# --- accounts ---


@router.get("/api/publish/accounts", response_model=c.PageResponse[c.PublishAccount])
def list_accounts(
    request: Request,
    client_id: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    include_archived: bool = False,
) -> c.PageResponse[c.PublishAccount]:
    require_role(request, c.UserRole.operator)
    return service.list_accounts(
        request, client_id=client_id, platform=platform, limit=limit, include_archived=include_archived
    )


@router.post("/api/publish/accounts", response_model=c.PublishAccount, status_code=201)
def create_account(payload: c.CreatePublishAccountRequest, request: Request) -> c.PublishAccount:
    require_role(request, c.UserRole.operator)
    return service.create_account(payload, request)


@router.patch("/api/publish/accounts/{account_id}", response_model=c.PublishAccount)
def patch_account(
    account_id: str, payload: c.PatchPublishAccountRequest, request: Request
) -> c.PublishAccount | JSONResponse:
    require_role(request, c.UserRole.operator)
    return service.patch_account(account_id, payload, request)


@router.delete("/api/publish/accounts/{account_id}", response_model=c.OkResponse)
def delete_account(account_id: str, request: Request) -> c.OkResponse | JSONResponse:
    require_role(request, c.UserRole.operator)
    return service.delete_account(account_id, request)


# --- case → account targets ---


@router.get(
    "/api/cases/{case_id}/publish-targets", response_model=c.PageResponse[c.CasePublishTarget]
)
def list_case_targets(case_id: str, request: Request) -> c.PageResponse[c.CasePublishTarget]:
    require_role(request, c.UserRole.operator)
    return service.list_case_targets(case_id, request)


@router.put(
    "/api/cases/{case_id}/publish-targets", response_model=c.PageResponse[c.CasePublishTarget]
)
def set_case_targets(
    case_id: str, payload: c.SetCasePublishTargetsRequest, request: Request
) -> c.PageResponse[c.CasePublishTarget]:
    require_role(request, c.UserRole.operator)
    return service.set_case_targets(case_id, payload, request)
