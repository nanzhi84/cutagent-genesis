"""Playwright browser-session driver for publishing-center QR login.

Drives a real browser (intended for the Mac Mini publishing host) to perform QR
login on 抖音/视频号/快手/小红书 creator backends and to validate persisted sessions.

Async Playwright work is bridged to this sync driver interface via a dedicated
thread + fresh event loop, so it never touches the caller's loop. Browser sessions
are held open between ``begin_login`` and ``poll_login`` until the scan completes
or ``close`` is called.

This driver is only constructed when ``CUTAGENT_PUBLISH_BROWSER_DRIVER=playwright``;
the sandbox default never imports it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import threading
import time
from typing import Any

from packages.core.storage.repository import new_id
from packages.core.workflow import NodeExecutionError
from packages.publishing.browser.driver import (
    PLAYWRIGHT_BROWSER_DRIVER,
    LoginHandle,
    LoginPollResult,
    SessionCheck,
    browser_unavailable,
)
from packages.publishing.browser.platforms import (
    PlatformLogin,
    QrCandidate,
    platform_login,
    select_best_qr_candidate,
    url_matches_logged_in_signal,
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _launch_kwargs(headless):
    kwargs = {"headless": headless, "args": ["--no-sandbox"]}
    proxy = (
        os.getenv("CUTAGENT_PUBLISH_BROWSER_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
    )
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return kwargs


def _run_async(coro: Any) -> Any:
    """Run a coroutine to completion on a fresh loop in a dedicated thread.

    Keeps the async Playwright work off the caller's event loop entirely, so the sync
    driver interface is safe to call from FastAPI's threadpool routes.
    """
    box: dict[str, Any] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised to the caller below
            box["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


async def _settle_page(page: Any, *, timeout_ms: int = 15000) -> None:
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    await page.wait_for_timeout(500)


async def _run_pre_steps(page: Any, login: PlatformLogin) -> None:
    for action, value in login.pre_steps:
        if action == "click_text":
            if not value:
                raise browser_unavailable(f"Login step {action!r} requires text.")
            await page.get_by_text(value, exact=True).first.click(timeout=30000)
        elif action == "click_qr_toggle_topright":
            await _click_qr_toggle_topright(page)
        else:
            raise browser_unavailable(f"Unsupported login pre-step: {action}")
        await _settle_page(page)


async def _click_qr_toggle_topright(page: Any) -> None:
    toggle_candidates: list[tuple[float, float, Any]] = []
    for frame in page.frames:
        with contextlib.suppress(Exception):
            elements = await frame.query_selector_all("img")
            for element in elements:
                box = await element.bounding_box()
                if box is None:
                    continue
                width = float(box["width"])
                height = float(box["height"])
                x = float(box["x"])
                y = float(box["y"])
                if 40 <= width <= 90 and 40 <= height <= 90 and x > 1000 and y < 330:
                    toggle_candidates.append((x, y, element))
    if not toggle_candidates:
        raise browser_unavailable("QR toggle image was not found in the login card top-right.")
    _x, _y, element = max(toggle_candidates, key=lambda item: (item[0], -item[1]))
    await element.click(timeout=15000)


async def _candidate_for_element(element: Any) -> QrCandidate | None:
    box = await element.bounding_box()
    if box is None:
        return None
    tag = await element.evaluate("element => element.tagName.toLowerCase()")
    class_name = await element.get_attribute("class")
    src = await element.get_attribute("src")
    return {
        "tag": tag if isinstance(tag, str) else "",
        "class": class_name or "",
        "src": src or "",
        "width": float(box["width"]),
        "height": float(box["height"]),
    }


async def _collect_qr_candidates(page: Any, login: PlatformLogin) -> list[tuple[QrCandidate, Any]]:
    frames = list(page.frames)
    frame_url_contains = login.qr.frame_url_contains
    if frame_url_contains:
        matching_frames = [frame for frame in frames if frame_url_contains in frame.url]
        if matching_frames:
            frames = matching_frames

    candidates: list[tuple[QrCandidate, Any]] = []
    for frame in frames:
        with contextlib.suppress(Exception):
            elements = await frame.query_selector_all(login.qr.candidate_selector)
            for element in elements:
                with contextlib.suppress(Exception):
                    candidate = await _candidate_for_element(element)
                    if candidate is not None:
                        candidates.append((candidate, element))
    return candidates


async def _find_qr_element(
    page: Any,
    login: PlatformLogin,
    *,
    timeout_ms: int = 30000,
) -> tuple[QrCandidate, Any]:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        pairs = await _collect_qr_candidates(page, login)
        best = select_best_qr_candidate([candidate for candidate, _element in pairs])
        if best is not None:
            for candidate, element in pairs:
                if candidate is best:
                    return candidate, element
        await page.wait_for_timeout(500)
    raise browser_unavailable("Login QR element not found on the login page.")


async def _page_has_any_text(page: Any, texts: tuple[str, ...]) -> bool:
    for frame in page.frames:
        for text in texts:
            with contextlib.suppress(Exception):
                if await frame.get_by_text(text).count() > 0:
                    return True
    return False


async def _refresh_expired_qr_if_needed(page: Any, login: PlatformLogin, element: Any) -> bool:
    if not login.qr_expired_texts:
        return False
    if not await _page_has_any_text(page, login.qr_expired_texts):
        return False
    await element.click(timeout=15000)
    await page.wait_for_timeout(1000)
    return True


async def _qr_data_url(element: Any, candidate: QrCandidate) -> str:
    src = candidate.get("src")
    if isinstance(src, str) and src.startswith("data:"):
        return src
    png = await element.screenshot()
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _raise_browser_unavailable(message: str, exc: Exception) -> None:
    if isinstance(exc, NodeExecutionError):
        raise exc
    raise browser_unavailable(f"{message}: {exc}") from exc


class PlaywrightBrowserDriver:
    """Real-browser driver. Held as a singleton on ``app.state``."""

    driver_id: str = PLAYWRIGHT_BROWSER_DRIVER

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        # login_token -> (playwright, browser, context, page, platform_login)
        self._sessions: dict[str, tuple[Any, Any, Any, Any, PlatformLogin]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _async_playwright():
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - optional/runtime dep on the host
            raise browser_unavailable(f"Playwright is not available: {exc}") from exc
        return async_playwright

    def begin_login(self, platform: str) -> LoginHandle:
        try:
            login = platform_login(platform)
        except KeyError as exc:
            raise browser_unavailable(
                f"Unsupported platform for browser login: {platform}"
            ) from exc
        async_playwright = self._async_playwright()
        token = new_id("login")

        async def _begin() -> str:
            pw: Any | None = None
            browser: Any | None = None
            try:
                pw = await async_playwright().start()
                browser = await pw.chromium.launch(**_launch_kwargs(self._headless))
                context = await browser.new_context(
                    user_agent=DESKTOP_UA,
                    viewport={"width": 1280, "height": 860},
                )
                page = await context.new_page()
                await page.goto(login.login_url, wait_until="networkidle", timeout=60000)
                await _run_pre_steps(page, login)
                candidate, element = await _find_qr_element(page, login)
                if await _refresh_expired_qr_if_needed(page, login, element):
                    candidate, element = await _find_qr_element(page, login)
                qr_image = await _qr_data_url(element, candidate)
                with self._lock:
                    self._sessions[token] = (pw, browser, context, page, login)
                return qr_image
            except Exception as exc:
                if browser is not None:
                    with contextlib.suppress(Exception):
                        await browser.close()
                if pw is not None:
                    with contextlib.suppress(Exception):
                        await pw.stop()
                _raise_browser_unavailable(f"Playwright login failed for {platform}", exc)
                raise AssertionError("unreachable")

        return LoginHandle(login_token=token, qr_image=_run_async(_begin()))

    def poll_login(self, login_token: str) -> LoginPollResult:
        with self._lock:
            entry = self._sessions.get(login_token)
        if entry is None:
            return LoginPollResult(status="failed", detail="unknown or closed login session")
        _pw, _browser, context, page, login = entry

        async def _poll() -> LoginPollResult:
            await _settle_page(page, timeout_ms=5000)
            if not url_matches_logged_in_signal(page.url, login.logged_in_signal):
                return LoginPollResult(status="pending")
            state = await context.storage_state()
            return LoginPollResult(status="success", storage_state_json=json.dumps(state))

        return _run_async(_poll())

    def validate_session(self, platform: str, storage_state_json: str) -> SessionCheck:
        try:
            login = platform_login(platform)
        except KeyError as exc:
            raise browser_unavailable(f"Unsupported platform: {platform}") from exc
        async_playwright = self._async_playwright()

        async def _validate() -> SessionCheck:
            pw: Any | None = None
            browser: Any | None = None
            try:
                pw = await async_playwright().start()
                browser = await pw.chromium.launch(**_launch_kwargs(self._headless))
                context = await browser.new_context(
                    user_agent=DESKTOP_UA,
                    storage_state=json.loads(storage_state_json),
                    viewport={"width": 1280, "height": 860},
                )
                page = await context.new_page()
                await page.goto(login.creator_home_url, wait_until="networkidle", timeout=60000)
                await _settle_page(page)
                active = url_matches_logged_in_signal(page.url, login.logged_in_signal)
                return SessionCheck(active=active)
            except Exception as exc:
                _raise_browser_unavailable(
                    f"Playwright session validation failed for {platform}",
                    exc,
                )
                raise AssertionError("unreachable")
            finally:
                if browser is not None:
                    with contextlib.suppress(Exception):
                        await browser.close()
                if pw is not None:
                    with contextlib.suppress(Exception):
                        await pw.stop()

        return _run_async(_validate())

    def close(self, login_token: str) -> None:
        with self._lock:
            entry = self._sessions.pop(login_token, None)
        if entry is None:
            return
        pw, browser, _context, _page, _login = entry

        async def _close() -> None:
            try:
                await browser.close()
            finally:
                await pw.stop()

        try:
            _run_async(_close())
        except Exception:  # pragma: no cover - cleanup is best-effort
            pass
