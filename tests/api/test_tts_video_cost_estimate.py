"""Standalone TTS / lip-sync cost-estimate endpoints.

These must produce a real number even when the provider gateway is
UNCONFIGURED (no matching published price catalog) by falling back to the
default catalog (origin fixed rates: TTS 0.15 CNY/1k chars, lip-sync 5.0
CNY/min). A configured catalog price always takes precedence.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.app import create_app
from packages.core import contracts as c


def _login(client: TestClient, email: str = "viewer@local.cutagent", password: str = "local-viewer") -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def _clear_price_catalog(app) -> None:
    app.state.repository.price_catalogs.clear()
    app.state.repository.price_items.clear()


def test_tts_estimate_uses_default_rate_when_gateway_unconfigured() -> None:
    app = create_app()
    with TestClient(app) as client:
        _clear_price_catalog(app)
        _login(client)
        # 1000 characters -> 1000/1000 * 0.15 = 0.15 CNY; duration 1000/5 = 200s.
        response = client.post("/api/tts/estimate-cost", json={"text": "x" * 1000})
        assert response.status_code == 200, response.text
        body = response.json()

    assert body["pricing_source"] == "default"
    assert body["text_length"] == 1000
    assert body["estimated_chars"] == 1000
    assert body["estimated_duration_sec"] == 200.0
    assert body["estimate"]["unpriced"] is False
    assert Decimal(body["estimate"]["unit_price"]["amount"]) == Decimal("0.00015")
    assert Decimal(body["estimate"]["estimated_cost"]["amount"]) == Decimal("0.15000")
    assert body["estimate"]["estimated_cost"]["currency"] == "CNY"


def test_lipsync_estimate_uses_default_rate_when_gateway_unconfigured() -> None:
    app = create_app()
    with TestClient(app) as client:
        _clear_price_catalog(app)
        _login(client)
        # 90 seconds -> 1.5 minutes * 5.0 = 7.5 CNY.
        response = client.post("/api/video/estimate-cost", json={"video_duration_sec": 90})
        assert response.status_code == 200, response.text
        body = response.json()

    assert body["pricing_source"] == "default"
    assert body["video_duration_sec"] == 90.0
    assert body["video_duration_min"] == 1.5
    assert body["estimate"]["unpriced"] is False
    assert Decimal(body["estimate"]["estimated_cost"]["amount"]) == Decimal("7.50")


def test_tts_estimate_prefers_published_catalog_price() -> None:
    app = create_app()
    with TestClient(app) as client:
        _clear_price_catalog(app)
        catalog = c.ProviderPriceCatalog(id="cat_cost", provider_id="sandbox", status="published")
        app.state.repository.price_catalogs[catalog.id] = catalog
        app.state.repository.price_items["pi_tts"] = c.ProviderPriceItem(
            id="pi_tts",
            catalog_id=catalog.id,
            provider_id="sandbox",
            model_id="*",
            capability_id="tts.speech",
            unit="input_token",
            unit_price=c.Money(amount=Decimal("0.001"), currency="CNY"),
        )
        _login(client)
        response = client.post("/api/tts/estimate-cost", json={"text": "x" * 100})
        assert response.status_code == 200, response.text
        body = response.json()

    assert body["pricing_source"] == "catalog"
    # 100 chars * 0.001 = 0.1 CNY.
    assert Decimal(body["estimate"]["estimated_cost"]["amount"]) == Decimal("0.100")


def test_cost_estimate_rejects_empty_and_nonpositive_inputs() -> None:
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/tts/estimate-cost", json={"text": ""}).status_code == 422
        assert client.post("/api/video/estimate-cost", json={"video_duration_sec": 0}).status_code == 422


def test_cost_estimate_requires_authentication() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.post("/api/tts/estimate-cost", json={"text": "hi"}).status_code == 401
        assert client.post("/api/video/estimate-cost", json={"video_duration_sec": 10}).status_code == 401
