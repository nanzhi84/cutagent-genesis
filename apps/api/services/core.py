from __future__ import annotations


from fastapi import Request

from apps.api.common import (
    repository,
    request_id,
)
from packages.core import contracts as c
from packages.core.observability import metric_snapshot

def health(request: Request) -> c.OkResponse:

    return c.OkResponse(request_id=request_id())


def metrics(request: Request) -> str:

    return metric_snapshot(repository(request))
