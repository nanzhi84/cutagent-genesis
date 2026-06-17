"""Guest-mode headless-browser media sniffing for Douyin (cookie-free fallback).

The browser glue (Playwright) is a thin adapter exercised live; here we test the
pure orchestration: filtering media responses, picking the streamed media URL,
formatting the captured cookie header, and the sniff_media error path. The real
browser is replaced with an injected ``capture`` returning canned raw data.
"""

from __future__ import annotations

import pytest

from packages.creative.reference_browser import (
    CaptureRaw,
    format_cookie_header,
    is_media_response,
    select_media_url,
    sniff_media,
)
from packages.creative.reference_extract import ReferenceExtractError


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_is_media_response_only_accepts_streamed_video():
    assert is_media_response("media", 200, "video/mp4")
    assert is_media_response("media", 206, "video/mp4; codecs=...")  # partial content
    assert not is_media_response("xhr", 200, "video/mp4")  # not a media request
    assert not is_media_response("media", 403, "video/mp4")  # blocked
    assert not is_media_response("media", 200, "application/json")  # not video
    assert not is_media_response("media", 200, None)


def test_select_media_url_prefers_last_streamed_then_router():
    # the actually-streamed (sniffed) media wins; the last one captured is freshest
    assert select_media_url(["https://cdn/a.mp4", "https://cdn/b.mp4"], []) == "https://cdn/b.mp4"
    # sniffed media beats router-data urls even when both are present
    assert select_media_url(["https://cdn/a.mp4"], ["https://cdn/router.mp4"]) == "https://cdn/a.mp4"
    # no sniffed media -> fall back to router_data play urls
    assert select_media_url([], ["https://cdn/router.mp4"]) == "https://cdn/router.mp4"
    assert select_media_url([], []) is None


def test_format_cookie_header_serializes_name_value_pairs():
    cookies = [
        {"name": "sessionid", "value": "abc", "domain": ".douyin.com"},
        {"name": "ttwid", "value": "xyz"},
        {"name": "blank"},  # no value -> skipped
    ]
    assert format_cookie_header(cookies) == "sessionid=abc; ttwid=xyz"


def test_sniff_media_returns_streamed_url_and_cookie_from_capture():
    async def fake_capture(url, *, cookie_header=None):
        return CaptureRaw(
            media_candidates=("https://cdn/v1.mp4", "https://cdn/v2.mp4"),
            router_play_urls=("https://cdn/router.mp4",),
            title="对标视频",
            duration_sec=42.0,
            resolved_url="https://www.douyin.com/video/123",
            cookies=({"name": "ttwid", "value": "xyz"},),
        )

    result = _run(sniff_media("https://v.douyin.com/abc/", capture=fake_capture))
    assert result.media_url == "https://cdn/v2.mp4"
    assert result.cookie_header == "ttwid=xyz"
    assert result.title == "对标视频"
    assert result.duration_sec == 42.0
    assert result.resolved_url == "https://www.douyin.com/video/123"


def test_sniff_media_raises_when_browser_captures_nothing():
    async def empty_capture(url, *, cookie_header=None):
        return CaptureRaw()

    with pytest.raises(ReferenceExtractError) as excinfo:
        _run(sniff_media("https://v.douyin.com/abc/", capture=empty_capture))
    assert excinfo.value.code.value.startswith("reference.")
