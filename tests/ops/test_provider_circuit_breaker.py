from __future__ import annotations

import json
import logging
import sqlite3
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from packages.ai.gateway.provider_gateway import ProviderCall, ProviderGateway
from packages.core.contracts import ErrorCode, ProviderStatus, utcnow
from packages.core.storage.database import ProviderInvocationRow
from packages.core.storage.repository import Repository
from packages.ops.circuit_breaker import ProviderCircuitBreaker
from packages.ops.provider_usage_metrics import sqlalchemy_provider_profile_health_metrics


sqlite3.register_adapter(dict, json.dumps)
sqlite3.register_adapter(list, json.dumps)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):
    return "JSON"


def _sqlite_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProviderInvocationRow.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _insert_invocation(
    session_factory,
    *,
    invocation_id: str,
    status: str,
    duration_ms: int,
    provider_profile_id: str = "sandbox.tts.default",
    started_offset_hours: int = 0,
    error_code: ErrorCode | None = None,
) -> None:
    started_at = utcnow() + timedelta(hours=started_offset_hours)
    with session_factory() as session:
        session.add(
            ProviderInvocationRow(
                id=invocation_id,
                provider_id="sandbox",
                model_id="tts.local",
                provider_profile_id=provider_profile_id,
                capability_id="tts.speech",
                status=status,
                duration_ms=duration_ms,
                billing_status="estimated",
                error=(
                    {"code": error_code.value, "message": error_code.value, "retryable": True}
                    if error_code is not None
                    else None
                ),
                started_at=started_at,
                finished_at=started_at,
                created_at=started_at,
                updated_at=started_at,
            )
        )
        session.commit()


def _seed_open_profile(session_factory) -> None:
    _insert_invocation(session_factory, invocation_id="pinv_success", status="succeeded", duration_ms=100)
    _insert_invocation(
        session_factory,
        invocation_id="pinv_failed",
        status="failed",
        duration_ms=200,
        error_code=ErrorCode.provider_remote_failed,
    )
    _insert_invocation(
        session_factory,
        invocation_id="pinv_timeout",
        status="timed_out",
        duration_ms=300,
        error_code=ErrorCode.provider_timeout,
    )
    _insert_invocation(
        session_factory,
        invocation_id="pinv_throttled",
        status="failed",
        duration_ms=1000,
        error_code=ErrorCode.provider_quota_exceeded,
    )
    _insert_invocation(
        session_factory,
        invocation_id="pinv_old_success",
        status="succeeded",
        duration_ms=10,
        started_offset_hours=-48,
    )


def test_provider_profile_health_metrics_computes_error_timeout_and_p95() -> None:
    session_factory = _sqlite_session_factory()
    _seed_open_profile(session_factory)

    metrics = sqlalchemy_provider_profile_health_metrics(
        session_factory,
        window_hours=24,
        error_rate_threshold=0.5,
    )

    profile = next(item for item in metrics if item.provider_profile_id == "sandbox.tts.default")
    assert profile.calls == 4
    assert profile.success_count == 1
    assert profile.failure_count == 3
    assert profile.timeout_or_throttle_count == 2
    assert profile.error_rate == 0.75
    assert profile.timeout_or_throttle_rate == 0.5
    assert profile.p95_latency_ms == 1000
    assert profile.circuit_open is True


def test_provider_circuit_breaker_blocks_open_profile_with_degradation(
    monkeypatch,
    caplog,
) -> None:
    session_factory = _sqlite_session_factory()
    _seed_open_profile(session_factory)
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_BREAKER", "1")
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_ERROR_RATE", "0.5")
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_WINDOW", "24")
    gateway = ProviderGateway(
        Repository(),
        circuit_breaker=ProviderCircuitBreaker(session_factory),
        auto_register_real_plugins=False,
    )

    with caplog.at_level(logging.WARNING, logger="packages.ops.circuit_breaker"):
        invocation, result = gateway.invoke(
            ProviderCall(
                provider_profile_id="sandbox.tts.default",
                capability_id="tts.speech",
                input={"text": "hello"},
            )
        )

    assert result is None
    assert invocation.status == ProviderStatus.failed
    assert invocation.error is not None
    assert invocation.error.code == ErrorCode.provider_remote_failed
    assert "circuit open" in invocation.error.message
    assert gateway.repository.usage_records == {}
    degradations = [
        record.__dict__.get("degradation")
        for record in caplog.records
        if record.__dict__.get("event") == "provider.circuit_open"
    ]
    assert any(item and item["code"] == "provider.circuit_open" for item in degradations)


def test_provider_circuit_breaker_allows_when_env_disabled_or_closed(monkeypatch) -> None:
    open_session_factory = _sqlite_session_factory()
    _seed_open_profile(open_session_factory)
    monkeypatch.delenv("CUTAGENT_PROVIDER_CIRCUIT_BREAKER", raising=False)
    gateway = ProviderGateway(
        Repository(),
        circuit_breaker=ProviderCircuitBreaker(open_session_factory),
        auto_register_real_plugins=False,
    )

    disabled_invocation, disabled_result = gateway.invoke(
        ProviderCall(
            provider_profile_id="sandbox.tts.default",
            capability_id="tts.speech",
            input={"text": "hello"},
        )
    )

    assert disabled_result is not None
    assert disabled_invocation.status == ProviderStatus.succeeded

    closed_session_factory = _sqlite_session_factory()
    _insert_invocation(closed_session_factory, invocation_id="pinv_closed_success_1", status="succeeded", duration_ms=80)
    _insert_invocation(closed_session_factory, invocation_id="pinv_closed_success_2", status="succeeded", duration_ms=90)
    _insert_invocation(
        closed_session_factory,
        invocation_id="pinv_closed_failed",
        status="failed",
        duration_ms=120,
        error_code=ErrorCode.provider_remote_failed,
    )
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_BREAKER", "1")
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_ERROR_RATE", "0.5")
    monkeypatch.setenv("CUTAGENT_PROVIDER_CIRCUIT_WINDOW", "24")
    closed_gateway = ProviderGateway(
        Repository(),
        circuit_breaker=ProviderCircuitBreaker(closed_session_factory),
        auto_register_real_plugins=False,
    )

    closed_invocation, closed_result = closed_gateway.invoke(
        ProviderCall(
            provider_profile_id="sandbox.tts.default",
            capability_id="tts.speech",
            input={"text": "hello"},
        )
    )

    assert closed_result is not None
    assert closed_invocation.status == ProviderStatus.succeeded
