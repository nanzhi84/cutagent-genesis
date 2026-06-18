"""Playwright browser driver platform config and QR-selection tests."""

from __future__ import annotations

import os

import pytest

from packages.publishing.browser.platforms import (
    PLATFORM_LOGINS,
    select_best_qr_candidate,
    url_matches_logged_in_signal,
)


def test_select_best_qr_candidate_prefers_square_data_url():
    ignored_toggle = {
        "tag": "img",
        "class": "login-toggle",
        "src": "data:image/png;base64,toggle",
        "width": 64,
        "height": 64,
    }
    ignored_canvas = {
        "tag": "canvas",
        "class": "decorative",
        "src": "",
        "width": 902,
        "height": 902,
    }
    plain_square = {
        "tag": "img",
        "class": "avatar",
        "src": "https://example.test/qr.png",
        "width": 180,
        "height": 178,
    }
    data_qr = {
        "tag": "img",
        "class": "login-code",
        "src": "data:image/png;base64,qr",
        "width": 176,
        "height": 176,
    }

    assert (
        select_best_qr_candidate([ignored_toggle, ignored_canvas, plain_square, data_qr])
        is data_qr
    )


def test_select_best_qr_candidate_rejects_toggle_icon_and_decorative_canvas():
    candidates = [
        {
            "tag": "img",
            "class": "qr-mode-toggle",
            "src": "data:image/png;base64,toggle",
            "width": 64,
            "height": 64,
        },
        {
            "tag": "canvas",
            "class": "background",
            "src": "",
            "width": 902,
            "height": 902,
        },
    ]

    assert select_best_qr_candidate(candidates) is None


def test_platform_login_configs_encode_verified_browser_flows():
    expected = {
        "douyin": {
            "login_url": "https://creator.douyin.com/",
            "pre_steps": (),
            "logged_in_signal": "creator-micro/home",
            "selector": "img[class*='qrcode'], canvas",
            "frame_url_contains": None,
        },
        "shipinhao": {
            "login_url": "https://channels.weixin.qq.com/platform",
            "pre_steps": (),
            "logged_in_signal": "!login",
            "selector": "img.qrcode, img[class*='qrcode'], canvas",
            "frame_url_contains": "login-for-iframe",
        },
        "kuaishou": {
            "login_url": "https://cp.kuaishou.com/",
            "pre_steps": (("click_text", "立即登录"), ("click_text", "扫码登录")),
            "logged_in_signal": "cp.kuaishou.com&&!passport",
            "selector": "img, canvas",
            "frame_url_contains": None,
        },
        "xiaohongshu": {
            "login_url": "https://creator.xiaohongshu.com/login",
            "pre_steps": (("click_qr_toggle_topright", None),),
            "logged_in_signal": "!/login",
            "selector": "img, canvas",
            "frame_url_contains": None,
        },
    }

    assert set(PLATFORM_LOGINS) == set(expected)
    for platform, fields in expected.items():
        login = PLATFORM_LOGINS[platform]
        assert login.login_url == fields["login_url"]
        assert login.pre_steps == fields["pre_steps"]
        assert login.logged_in_signal == fields["logged_in_signal"]
        assert login.qr.candidate_selector == fields["selector"]
        assert login.qr.frame_url_contains == fields["frame_url_contains"]


def test_url_matches_logged_in_signal_supports_contains_and_excludes():
    assert url_matches_logged_in_signal(
        "https://creator.douyin.com/creator-micro/home",
        "creator-micro/home",
    )
    assert url_matches_logged_in_signal(
        "https://cp.kuaishou.com/article/manage/video",
        "cp.kuaishou.com&&!passport",
    )
    assert not url_matches_logged_in_signal(
        "https://passport.kuaishou.com/login",
        "cp.kuaishou.com&&!passport",
    )
    assert url_matches_logged_in_signal("https://channels.weixin.qq.com/platform", "!login")
    assert not url_matches_logged_in_signal(
        "https://channels.weixin.qq.com/platform/login.html",
        "!login",
    )


def test_live_douyin_playwright_login_fetches_qr_data_url():
    if os.getenv("CUTAGENT_RUN_BROWSER_TESTS") != "1":
        pytest.skip("set CUTAGENT_RUN_BROWSER_TESTS=1 to run live Playwright browser test")

    from packages.publishing.browser.playwright_driver import PlaywrightBrowserDriver

    driver = PlaywrightBrowserDriver()
    handle = driver.begin_login("douyin")
    try:
        assert handle.qr_image.startswith("data:image/")
    finally:
        driver.close(handle.login_token)
