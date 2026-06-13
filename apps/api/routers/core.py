from __future__ import annotations


from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from apps.api.services import core as service
from packages.core import contracts as c

router = APIRouter()

@router.get("/api/health", response_model=c.OkResponse)
def health(request: Request) -> c.OkResponse:

    return service.health(request)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> str:

    return service.metrics(request)
