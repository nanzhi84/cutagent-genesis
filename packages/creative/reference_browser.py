"""Guest-mode headless-browser media sniffing (cookie-free Douyin fallback).

When the plain HTTP share-page parse / yt-dlp path is blocked without login
cookies, a real (headless) browser visiting the link as an anonymous guest plays
the video and we intercept the actual video stream URL off the network — no
literal screen recording, no virtual audio device. The streamed MP4 is then
downloaded + transcribed by the existing reference pipeline.

The Playwright glue (`_playwright_capture`) is a thin adapter exercised live; the
orchestration + selection logic is pure and unit-tested with an injected capture.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from packages.core import contracts as c
from packages.creative.reference_extract import (
    ReferenceExtractError,
    _find_douyin_item,
    _parse_router_data,
)

# A real mobile visitor UA — Douyin serves the lightweight mobile web player that
# exposes the video stream to a guest more readily than the desktop page.
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class CaptureRaw:
    """Raw output of one browser capture pass (everything the page surfaced)."""

    media_candidates: tuple[str, ...] = ()
    router_play_urls: tuple[str, ...] = ()
    title: str | None = None
    duration_sec: float | None = None
    resolved_url: str | None = None
    cookies: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class BrowserMediaResult:
    media_url: str
    cookie_header: str
    title: str | None = None
    duration_sec: float | None = None
    resolved_url: str | None = None


CaptureFn = Callable[..., Awaitable[CaptureRaw]]


def is_media_response(resource_type: str, status: int, content_type: str | None) -> bool:
    """A network response carrying a playable video stream worth downloading."""
    return (
        resource_type == "media"
        and status in (200, 206)
        and "video" in (content_type or "").lower()
    )


def select_media_url(media_candidates: list[str], router_play_urls: list[str]) -> str | None:
    """Pick the stream to download: the freshest actually-streamed media wins;
    router-data play urls are only a fallback when nothing was sniffed."""
    if media_candidates:
        return media_candidates[-1]
    if router_play_urls:
        return router_play_urls[-1]
    return None


def format_cookie_header(cookies: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str:
    parts = [
        f"{ck['name']}={ck['value']}"
        for ck in cookies
        if ck.get("name") and ck.get("value") is not None
    ]
    return "; ".join(parts)


async def sniff_media(
    url: str,
    *,
    cookie_header: str | None = None,
    capture: CaptureFn | None = None,
) -> BrowserMediaResult:
    """Drive a guest browser to surface the video stream URL for ``url``.

    ``capture`` is injectable (defaults to the real Playwright adapter) so the
    pure selection/error logic is unit-testable without a browser.
    """
    cap = capture or _playwright_capture
    raw = await cap(url, cookie_header=cookie_header)
    media_url = select_media_url(list(raw.media_candidates), list(raw.router_play_urls))
    if not media_url:
        raise ReferenceExtractError(
            c.ErrorCode.reference_unreachable,
            "Headless browser could not capture a video stream (guest mode may be rate-limited).",
            details={"url": url},
        )
    header = format_cookie_header(raw.cookies) or (cookie_header or "")
    return BrowserMediaResult(
        media_url=media_url,
        cookie_header=header,
        title=raw.title,
        duration_sec=raw.duration_sec,
        resolved_url=raw.resolved_url or url,
    )


def _cookie_header_to_playwright(header: str, *, domain: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, _, value = part.strip().partition("=")
        if name and value:
            cookies.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return cookies


def _douyin_play_urls_from_content(content: str) -> list[str]:
    router = _parse_router_data(content)
    item = _find_douyin_item(router) if router else {}
    urls: list[str] = []
    _collect_url_lists(item, urls)
    # de-dup, keep order, normalize protocol-relative urls
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        normalized = ("https:" + raw) if raw.startswith("//") else raw
        if normalized.startswith("http") and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _collect_url_lists(value: Any, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "url_list" and isinstance(nested, list):
                out.extend(str(item) for item in nested if isinstance(item, str))
            else:
                _collect_url_lists(nested, out)
    elif isinstance(value, list):
        for nested in value:
            _collect_url_lists(nested, out)


async def _playwright_capture(
    url: str,
    *,
    cookie_header: str | None = None,
    nav_timeout_ms: int = 60000,
    settle_ms: int = 2500,
    max_wait_iters: int = 30,
) -> CaptureRaw:  # pragma: no cover - exercised live, not in unit tests
    from playwright.async_api import async_playwright

    media_candidates: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=MOBILE_USER_AGENT,
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                device_scale_factor=3,
            )
            if cookie_header:
                injected = _cookie_header_to_playwright(cookie_header, domain=".douyin.com")
                if injected:
                    await context.add_cookies(injected)
            page = await context.new_page()

            async def _on_response(response: Any) -> None:
                try:
                    if response.status not in (200, 206):
                        return
                    headers = await response.all_headers()
                    if is_media_response(
                        response.request.resource_type,
                        response.status,
                        str(headers.get("content-type") or ""),
                    ):
                        media_candidates.append(response.url)
                except Exception:
                    pass

            page.on("response", lambda response: asyncio.create_task(_on_response(response)))
            await page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            await page.wait_for_timeout(settle_ms)

            router_urls = _douyin_play_urls_from_content(await page.content())
            meta = await page.evaluate(
                """() => {
                  const title = (document.title || '').replace(/\\s*-\\s*抖音\\s*$/, '').trim();
                  const desc = document.querySelector('meta[property=\"og:description\"]')?.getAttribute('content') || '';
                  const video = document.querySelector('video');
                  return { title, description: desc, resolved_url: location.href, duration: (video && video.duration) || 0 };
                }"""
            )
            try:
                await page.evaluate(
                    "async () => { const v = document.querySelector('video'); if (v) { await v.play(); } }"
                )
            except Exception:
                pass

            for _ in range(max_wait_iters):
                if media_candidates:
                    break
                await page.wait_for_timeout(500)

            cookies = await context.cookies()
        finally:
            await browser.close()

    duration = float(meta.get("duration") or 0) or None
    return CaptureRaw(
        media_candidates=tuple(media_candidates),
        router_play_urls=tuple(router_urls),
        title=(str(meta.get("title")).strip() or None) if meta.get("title") else None,
        duration_sec=duration,
        resolved_url=str(meta.get("resolved_url") or url),
        cookies=tuple(cookies),
    )
