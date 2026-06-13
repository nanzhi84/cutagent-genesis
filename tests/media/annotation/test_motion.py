from __future__ import annotations

from packages.media.annotation.sensors import MotionGuard
from tests.media.annotation.fixtures import make_multi_cut_video


def test_motion_guard_windows_only_portrait_edges():
    mg = MotionGuard(portrait_edge_window=1.5)
    # Non-portrait -> no windows.
    assert mg.motion_guard_windows(total_duration=10.0, video_type="scenery") == []
    # Too short -> no windows.
    assert mg.motion_guard_windows(total_duration=0.5, video_type="portrait") == []
    # Portrait long enough -> head + tail.
    windows = mg.motion_guard_windows(total_duration=10.0, video_type="portrait")
    labels = [w[0] for w in windows]
    assert "head" in labels and "tail" in labels


def test_build_event_camera_drop_from_metrics():
    mg = MotionGuard()
    # Synthetic tail metrics describing a sustained vertical sink.
    metrics = {
        "start": 8.0,
        "end": 10.0,
        "pairs": 20,
        "mag_p95_px360": 12.0,
        "active_ratio": 0.9,
        "hard_ratio": 0.6,
        "max_active_run_pairs": 18,
        "cum_x_range_px360": 10.0,
        "cum_y_range_px360": 60.0,
        "net_y_px360": 40.0,
        "straightness_ratio": 0.5,
        "direction_flip_ratio": 0.1,
        "jerk_p90_px360": 3.0,
        "residual_to_p95_ratio": 0.4,
    }
    event = mg.build_motion_guard_event_from_metrics(
        metrics, label="tail", total_duration=10.0
    )
    assert event is not None
    assert event["event_type"] == "camera_drop"
    assert event["risk_tier"] == "hard"
    assert event["source"] == "motion_guard"


def test_build_event_returns_none_for_calm_metrics():
    mg = MotionGuard()
    calm = {
        "start": 0.0,
        "end": 2.0,
        "pairs": 20,
        "mag_p95_px360": 1.0,
        "active_ratio": 0.05,
        "hard_ratio": 0.0,
        "max_active_run_pairs": 1,
        "cum_x_range_px360": 2.0,
        "cum_y_range_px360": 2.0,
        "net_y_px360": 1.0,
        "straightness_ratio": 0.9,
        "direction_flip_ratio": 0.05,
        "jerk_p90_px360": 0.5,
        "residual_to_p95_ratio": 0.2,
    }
    assert mg.build_motion_guard_event_from_metrics(
        calm, label="head", total_duration=10.0
    ) is None


def test_build_event_requires_minimum_pairs_and_duration():
    mg = MotionGuard()
    too_few = {"start": 0.0, "end": 2.0, "pairs": 2}
    assert mg.build_motion_guard_event_from_metrics(
        too_few, label="head", total_duration=10.0
    ) is None


def test_detect_motion_guard_events_no_false_positive_on_static_clip(tmp_path):
    # A solid-color (static) clip has no real camera motion -> no events.
    video = make_multi_cut_video(tmp_path, seg_dur=2.0, width=320, height=568)
    mg = MotionGuard()
    result = mg.detect_motion_guard_events(
        str(video), total_duration=6.0, video_type="portrait"
    )
    assert result["enabled"] is True
    assert result["events"] == []


def test_detect_motion_guard_disabled_returns_empty():
    mg = MotionGuard(motion_guard_enabled=False)
    result = mg.detect_motion_guard_events(
        "irrelevant.mp4", total_duration=10.0, video_type="portrait"
    )
    assert result["events"] == []
    assert result["windows"] == []
