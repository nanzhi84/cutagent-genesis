from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_annotation_player_timeline_segments_do_not_capture_scrubber_input() -> None:
    player = _read("apps/web/src/components/ui/VideoPlayer.tsx")
    modal = _read("apps/web/src/components/annotation/AnnotationEditorModal.tsx")

    assert "segmentBarsInteractive?: boolean" in player
    assert "segmentBarsInteractive = true" in player
    assert "pointer-events-none" in player
    assert "segmentBarsInteractive={false}" in modal


def test_bgm_readonly_segments_are_clickable_seek_targets() -> None:
    modal = _read("apps/web/src/components/annotation/AnnotationEditorModal.tsx")

    assert "seekRequest={seekRequest}" in modal
    assert "onSelectSegment={seekToBgmSegment}" in modal
    assert "onClick={() => onSelectSegment?.(item)}" in modal
    assert "BgmSegmentTimeline segments={segments}" in modal


def test_video_readonly_segments_are_clickable_seek_targets() -> None:
    modal = _read("apps/web/src/components/annotation/AnnotationEditorModal.tsx")

    assert "onSelectSegment={seekToVisualSegment}" in modal
    assert "onSelectSegment: (segment: AnnotationTimelineSegment) => void;" in modal
    assert "onSelect={() => onSelectSegment(segment)}" in modal


def test_video_usage_copy_distinguishes_portrait_original_from_broll_cover() -> None:
    modal = _read("apps/web/src/components/annotation/AnnotationEditorModal.tsx")

    assert "适合盖旁白" not in modal
    assert "仅盖旁白" not in modal
    assert "原片承接" not in modal
    assert "不适合数字人口型" in modal
    assert "适合做 B-roll" in modal
    assert "只做 B-roll" in modal
