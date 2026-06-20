"""Pure timeline frame-grid helpers shared by production planning nodes."""

from __future__ import annotations

import math

from packages.core.contracts.artifacts import TimelineTrackSegment, TimelineValidationReport

BROLL_PORTRAIT_CUT_SNAP_MAX_FRAMES = 15
BROLL_MIN_VISIBLE_AROLL_SECONDS = 3.0


def to_frame(seconds: float, fps: int) -> int:
    # Keep the round-half-up boundary invariant from planning.editing.frame_grid.
    return max(0, int(math.floor(float(seconds) * fps + 0.5)))


def _timeline_start(segment: dict, fps: int) -> int:
    if segment["timeline_start_frame"] is not None:
        return segment["timeline_start_frame"]
    return to_frame(segment["start_sec"], fps)


def _timeline_end(segment: dict, fps: int) -> int:
    if segment["timeline_end_frame"] is not None:
        return segment["timeline_end_frame"]
    return to_frame(segment["end_sec"], fps)


def _source_start(segment: dict, fps: int) -> int:
    if segment["source_start_frame"] is not None:
        return segment["source_start_frame"]
    return to_frame(segment.get("source_start_sec", segment["start_sec"]), fps)


def _source_end(segment: dict, fps: int) -> int:
    if segment["source_end_frame"] is not None:
        return segment["source_end_frame"]
    return to_frame(segment.get("source_end_sec", segment["end_sec"]), fps)


def build_tracks(raw_segments: list[dict], fps: int) -> list[TimelineTrackSegment]:
    return [
        TimelineTrackSegment(
            track_id=segment["track_id"],
            segment_id=segment["segment_id"],
            asset_ref=segment["asset_ref"],
            timeline_start_frame=_timeline_start(segment, fps),
            timeline_end_frame=_timeline_end(segment, fps),
            source_start_frame=_source_start(segment, fps),
            source_end_frame=_source_end(segment, fps),
        )
        for segment in raw_segments
    ]


def align_broll_to_portrait_cuts(
    raw_segments: list[dict],
    fps: int,
    *,
    max_gap_frames: int = BROLL_PORTRAIT_CUT_SNAP_MAX_FRAMES,
    min_visible_aroll_frames: int | None = None,
) -> list[dict]:
    """Snap near-missed B-roll overlays to adjacent portrait cut frames."""
    residual_limit = (
        max(0, int(min_visible_aroll_frames))
        if min_visible_aroll_frames is not None
        else to_frame(BROLL_MIN_VISIBLE_AROLL_SECONDS, fps)
    )
    if max_gap_frames <= 0 and residual_limit <= 0:
        return list(raw_segments)

    portrait_windows = sorted(
        (
            (_timeline_start(segment, fps), _timeline_end(segment, fps))
            for segment in raw_segments
            if segment["track_id"] == "portrait"
        ),
        key=lambda window: window[0],
    )
    portrait_windows = [
        (start, end)
        for start, end in portrait_windows
        if end > start
    ]
    if not portrait_windows:
        return list(raw_segments)

    broll_starts_by_index = {
        index: _timeline_start(segment, fps)
        for index, segment in enumerate(raw_segments)
        if segment["track_id"] == "broll"
    }
    broll_indices = sorted(broll_starts_by_index, key=lambda index: broll_starts_by_index[index])
    next_broll_start: dict[int, int] = {}
    for position, index in enumerate(broll_indices[:-1]):
        next_broll_start[index] = broll_starts_by_index[broll_indices[position + 1]]
    previous_broll_end: dict[int, int] = {}
    for position, index in enumerate(broll_indices[1:], start=1):
        previous_index = broll_indices[position - 1]
        previous_broll_end[index] = _timeline_end(raw_segments[previous_index], fps)

    def should_snap(residual_frames: int) -> bool:
        if residual_frames <= 0:
            return False
        return (
            (residual_limit > 0 and residual_frames < residual_limit)
            or (max_gap_frames > 0 and residual_frames <= max_gap_frames)
        )

    aligned: list[dict] = []
    for index, segment in enumerate(raw_segments):
        if segment["track_id"] != "broll":
            aligned.append(segment)
            continue

        start_frame = _timeline_start(segment, fps)
        end_frame = _timeline_end(segment, fps)
        source_start_frame = _source_start(segment, fps)
        if end_frame <= start_frame:
            aligned.append(segment)
            continue

        new_start = start_frame
        new_end = end_frame
        for portrait_start, portrait_end in portrait_windows:
            if portrait_end <= new_start or portrait_start >= new_end:
                continue
            if portrait_start < new_start < portrait_end:
                head_residual = new_start - portrait_start
                if should_snap(head_residual):
                    new_start = portrait_start
            if portrait_start < new_end < portrait_end:
                tail_residual = portrait_end - new_end
                if should_snap(tail_residual):
                    new_end = portrait_end

        start_delta = start_frame - new_start
        if start_delta > source_start_frame:
            continue

        preceding_broll_end = previous_broll_end.get(index)
        following_broll_start = next_broll_start.get(index)
        if (
            new_end <= new_start
            or (preceding_broll_end is not None and new_start < preceding_broll_end)
            or (following_broll_start is not None and new_end > following_broll_start)
        ):
            continue

        if new_start != start_frame or new_end != end_frame:
            new_source_start = source_start_frame - start_delta
            adjusted = dict(segment)
            adjusted["timeline_start_frame"] = new_start
            adjusted["timeline_end_frame"] = new_end
            adjusted["source_start_frame"] = new_source_start
            adjusted["source_end_frame"] = new_source_start + (new_end - new_start)
            adjusted["start_sec"] = round(new_start / fps, 3)
            adjusted["end_sec"] = round(new_end / fps, 3)
            adjusted["source_start_sec"] = round(new_source_start / fps, 3)
            adjusted["source_end_sec"] = round(adjusted["source_end_frame"] / fps, 3)
            aligned.append(adjusted)
        else:
            aligned.append(segment)

    return aligned


def validate_timeline(
    raw_segments: list[dict],
    fps: int,
    total_frames: int,
) -> TimelineValidationReport:
    """Validate overlap, negative duration, and bounds checks per the legacy node."""
    negative_duration = any(
        _timeline_end(segment, fps) <= _timeline_start(segment, fps) for segment in raw_segments
    )
    out_of_bounds = any(
        _timeline_start(segment, fps) < 0 or _timeline_end(segment, fps) > total_frames
        for segment in raw_segments
    )
    overlap = False
    by_track: dict[str, list[dict]] = {}
    for segment in raw_segments:
        by_track.setdefault(segment["track_id"], []).append(segment)
    for segments in by_track.values():
        ordered = sorted(segments, key=lambda segment: _timeline_start(segment, fps))
        previous_end = None
        for segment in ordered:
            if previous_end is not None and _timeline_start(segment, fps) < previous_end:
                overlap = True
            segment_end = _timeline_end(segment, fps)
            previous_end = max(previous_end or segment_end, segment_end)
    return TimelineValidationReport(
        valid=not (negative_duration or out_of_bounds or overlap),
        checks={
            "overlap": not overlap,
            "negative_duration": not negative_duration,
            "out_of_bounds": not out_of_bounds,
        },
    )
