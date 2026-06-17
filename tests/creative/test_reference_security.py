"""Security hardening for reference extraction: exact host allowlist (no substring
platform spoofing), SSRF guard (reject non-public resolved IPs), and scoping the
stored Douyin login cookie to douyin hosts only (no credential leak)."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from packages.creative import reference_extract as R
from packages.creative.reference_extract import (
    ReferenceExtractError,
    _assert_public_url,
    _is_douyin_host,
    _platform_from_host,
)

from tests.creative.test_reference_extract import (  # reuse fixtures
    FakeObjectStore,
    FakeSecretStore,
    FakeYDL,
    _patch_to_thread,
)


def _run(value):
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def test_platform_from_host_is_exact_not_substring():
    assert _platform_from_host("v.douyin.com") == "douyin"
    assert _platform_from_host("www.douyin.com") == "douyin"
    assert _platform_from_host("douyin.com") == "douyin"
    assert _platform_from_host("www.iesdouyin.com") == "douyin"
    # attacker hosts that merely CONTAIN 'douyin' must NOT opt into the douyin path
    assert _platform_from_host("douyin.attacker.com") == "generic"
    assert _platform_from_host("evildouyin.com") == "generic"
    assert _platform_from_host("169.254.169.254.douyin.example") == "generic"
    assert _platform_from_host("www.youtube.com") == "youtube"


def test_is_douyin_host_exact_suffix():
    assert _is_douyin_host("v.douyin.com")
    assert _is_douyin_host("iesdouyin.com")
    assert not _is_douyin_host("douyin.attacker.com")
    assert not _is_douyin_host("notdouyin.com")


def test_assert_public_url_rejects_private_and_loopback():
    def fake_resolve_private(host, port):
        return [(2, 1, 6, "", ("169.254.169.254", 0))]

    with pytest.raises(ReferenceExtractError):
        _assert_public_url("http://metadata.internal/latest", resolve=fake_resolve_private)

    def fake_resolve_loopback(host, port):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    with pytest.raises(ReferenceExtractError):
        _assert_public_url("http://localhost.evil.com/", resolve=fake_resolve_loopback)


def test_assert_public_url_allows_public():
    def fake_resolve_public(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    parsed = _assert_public_url("https://www.douyin.com/video/1", resolve=fake_resolve_public)
    assert parsed.hostname == "www.douyin.com"


def test_assert_public_url_allows_proxy_fake_ip_range():
    # Fake-IP proxies (Clash etc.) map external domains into 198.18.0.0/15 (RFC 2544
    # benchmark range). It is non-routable and not an internal-service range, so the
    # SSRF guard must not reject it (otherwise extraction breaks behind such proxies).
    def fake_resolve_fakeip(host, port):
        return [(2, 1, 6, "", ("198.18.3.137", 0))]

    parsed = _assert_public_url("https://v.douyin.com/abc/", resolve=fake_resolve_fakeip)
    assert parsed.hostname == "v.douyin.com"


def test_stored_douyin_cookie_not_sent_to_non_douyin_host(monkeypatch: pytest.MonkeyPatch):
    # A stored Douyin login cookie must NOT be attached when extracting a youtube URL.
    module = R
    _patch_to_thread(module, monkeypatch)
    FakeYDL.info = {
        "title": "yt",
        "extractor_key": "Youtube",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://sub.example/en.vtt"}]},
    }
    monkeypatch.setattr(module, "_load_youtube_dl", lambda: FakeYDL)
    monkeypatch.setattr(module, "_assert_public_url", lambda url, **k: module._supported_url(url))

    seen_headers: list[dict] = []

    async def capture_info(url: str, *, headers: dict[str, str]) -> dict:
        seen_headers.append(dict(headers))
        return dict(FakeYDL.info)

    monkeypatch.setattr(module, "_extract_info", capture_info)

    async def fake_get_text(url: str, headers=None) -> str:
        return "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello"

    monkeypatch.setattr(module, "_http_get_text", fake_get_text)

    _run(
        module.extract_reference(
            "https://www.youtube.com/watch?v=abc",
            "en",
            asr_invoke=lambda a, b: "x",
            object_store=FakeObjectStore(),
            secret_store=FakeSecretStore({"douyin_cookie": "sessionid=secret"}),
        )
    )
    assert seen_headers, "expected _extract_info to be called"
    assert "Cookie" not in seen_headers[0], "douyin cookie leaked to youtube host"
