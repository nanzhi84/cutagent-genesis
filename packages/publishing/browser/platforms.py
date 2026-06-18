"""Per-platform login + creator-backend endpoints for the Playwright driver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

LoginStep = tuple[str, str | None]
QrCandidate = Mapping[str, object]


@dataclass(frozen=True)
class QrLocator:
    candidate_selector: str
    frame_url_contains: str | None = None


@dataclass(frozen=True)
class PlatformLogin:
    platform: str
    login_url: str
    creator_home_url: str
    qr: QrLocator
    logged_in_signal: str
    pre_steps: tuple[LoginStep, ...] = ()
    qr_expired_texts: tuple[str, ...] = ()


def _candidate_text(candidate: QrCandidate, key: str) -> str:
    value = candidate.get(key)
    return value if isinstance(value, str) else ""


def _candidate_size(candidate: QrCandidate, key: str) -> float:
    value = candidate.get(key)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def select_best_qr_candidate(candidates: list[QrCandidate]) -> QrCandidate | None:
    """Choose the best QR-looking element candidate without touching browser APIs."""
    best: QrCandidate | None = None
    best_score: tuple[int, int, int, float] | None = None
    for candidate in candidates:
        width = _candidate_size(candidate, "width")
        height = _candidate_size(candidate, "height")
        if abs(width - height) >= 40:
            continue
        if not (140 <= width <= 280 and 140 <= height <= 280):
            continue

        class_name = _candidate_text(candidate, "class").lower()
        src = _candidate_text(candidate, "src")
        has_qrcode_class = "qrcode" in class_name
        has_data_src = src.startswith("data:")
        preferred = has_qrcode_class or has_data_src
        score = (
            1 if preferred else 0,
            1 if has_qrcode_class else 0,
            1 if has_data_src else 0,
            min(width, height),
        )
        if best_score is None or score > best_score:
            best = candidate
            best_score = score
    return best


def url_matches_logged_in_signal(url: str, logged_in_signal: str) -> bool:
    """Evaluate a serializable URL signal: ``foo&&!bar`` means contains foo, excludes bar."""
    parts = tuple(part.strip() for part in logged_in_signal.split("&&") if part.strip())
    if not parts:
        return False
    for part in parts:
        if part.startswith("!"):
            if part[1:] in url:
                return False
            continue
        if part not in url:
            return False
    return True


PLATFORM_LOGINS: dict[str, PlatformLogin] = {
    "douyin": PlatformLogin(
        platform="douyin",
        login_url="https://creator.douyin.com/",
        creator_home_url="https://creator.douyin.com/creator-micro/home",
        qr=QrLocator(candidate_selector="img[class*='qrcode'], canvas"),
        logged_in_signal="creator-micro/home",
        qr_expired_texts=("二维码失效", "点击刷新"),
    ),
    "kuaishou": PlatformLogin(
        platform="kuaishou",
        login_url="https://cp.kuaishou.com/",
        creator_home_url="https://cp.kuaishou.com/article/manage/video",
        qr=QrLocator(candidate_selector="img, canvas"),
        logged_in_signal="cp.kuaishou.com&&!passport",
        pre_steps=(("click_text", "立即登录"), ("click_text", "扫码登录")),
    ),
    "shipinhao": PlatformLogin(
        platform="shipinhao",
        login_url="https://channels.weixin.qq.com/platform",
        creator_home_url="https://channels.weixin.qq.com/platform/home",
        qr=QrLocator(
            candidate_selector="img.qrcode, img[class*='qrcode'], canvas",
            frame_url_contains="login-for-iframe",
        ),
        logged_in_signal="!login",
    ),
    "xiaohongshu": PlatformLogin(
        platform="xiaohongshu",
        login_url="https://creator.xiaohongshu.com/login",
        creator_home_url="https://creator.xiaohongshu.com/new/home",
        qr=QrLocator(candidate_selector="img, canvas"),
        logged_in_signal="!/login",
        pre_steps=(("click_qr_toggle_topright", None),),
    ),
}


def platform_login(platform: str) -> PlatformLogin:
    login = PLATFORM_LOGINS.get(platform)
    if login is None:
        raise KeyError(platform)
    return login
