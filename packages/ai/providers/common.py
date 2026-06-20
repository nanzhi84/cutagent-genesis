from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

import httpx

from packages.ai.gateway.provider_context import ProviderInvocationContext
from packages.ai.gateway.provider_gateway import ProviderRuntimeError
from packages.core.contracts import ErrorCode, Money


def require_secret(context: ProviderInvocationContext) -> str:
    secret = context.get_secret()
    if not secret:
        raise ProviderRuntimeError(ErrorCode.provider_auth_failed, "Provider secret is missing.")
    return secret


def option(context: ProviderInvocationContext, name: str, default: Any = None) -> Any:
    return context.profile.default_options.get(name, default)


def poll_budget(
    options: dict[str, Any],
    *,
    default_interval: float,
    default_max_attempts: int,
    timeout_minutes: Any = None,
) -> tuple[float, int]:
    interval = float(options["poll_interval"] if options.get("poll_interval") is not None else default_interval)
    max_attempts = int(
        options["poll_max_attempts"] if options.get("poll_max_attempts") is not None else default_max_attempts
    )
    requested_minutes = _float_or_none(timeout_minutes)
    if requested_minutes is None or requested_minutes <= 0 or interval <= 0:
        return interval, max_attempts
    requested_attempts = max(1, math.ceil((requested_minutes * 60.0) / interval))
    return interval, max(max_attempts, requested_attempts)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money_cny(amount: Decimal | int | str) -> Money:
    return Money(amount=Decimal(str(amount)), currency="CNY")


def map_http_status(status_code: int, body: str = "") -> ProviderRuntimeError:
    if status_code in {401, 403}:
        return ProviderRuntimeError(ErrorCode.provider_auth_failed, f"Provider auth failed: HTTP {status_code}.")
    if status_code == 429:
        return ProviderRuntimeError(ErrorCode.provider_quota_exceeded, "Provider quota exceeded.")
    return ProviderRuntimeError(
        ErrorCode.provider_remote_failed,
        f"Provider request failed: HTTP {status_code} {body[:160]}".strip(),
    )


def request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    try:
        response = client.request(
            method,
            url,
            headers=headers,
            json=json_body,
            data=data,
            files=files,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderRuntimeError(ErrorCode.provider_timeout, "Provider request timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRuntimeError(ErrorCode.provider_remote_failed, str(exc)) from exc
    if response.status_code >= 400:
        raise map_http_status(response.status_code, response.text)
    return response


def response_json(response: httpx.Response) -> dict[str, Any]:
    payload = response_json_value(response)
    if not isinstance(payload, dict):
        raise ProviderRuntimeError(ErrorCode.provider_remote_failed, "Provider returned non-object JSON.")
    return payload


def response_json_value(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderRuntimeError(ErrorCode.provider_remote_failed, "Provider returned invalid JSON.") from exc
    return payload


def extract_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("data", "result", "output"):
            if key in payload:
                return payload[key]
    return payload


def first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None
