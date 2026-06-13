"""Media-domain annotation package: pure CV/VAD/scene-detection sensor suite.

This is the deterministic, key-free half of the b-roll analyzer: shot-cut
detection, voice-activity detection, picture-quality (black/freeze/blur),
motion-guard (shake/camera-drop), face counting, frame extraction, clip-boundary
defences, window planning, and the deterministic whole-clip quality report.

No network, no VLM/LLM calls, no remote keys - pure local CV/DSP. The VLM
annotation layer and pipeline wiring are out of scope (a later step). The
artifact shapes these sensors feed (AnnotationV4 / ClipV4 / windows / quality
report) live in ``packages.core.contracts``.
"""

from __future__ import annotations

from .boundary import apply_safety_inset, has_internal_cut, snap_to_cuts
from .errors import (
    AnnotationV4Error,
    RuntimeVLMError,
    SchemaError,
    SemanticError,
    UnrecoverableError,
)
from .report import build_quality_report, merged_event_duration
from .sensors import (
    MotionGuard,
    count_faces_in_image,
    detect_cv_quality_events,
    detect_shot_cuts,
    detect_speech_islands,
    extract_frame_at_time,
    extract_frames_for_times,
    max_faces_in_frame_paths,
    merge_blur_segments,
    merge_speech_probabilities,
    parse_blackdetect,
    parse_freezedetect,
    reset_detector_cache,
)
from .windows import plan_windows

__all__ = [
    # sensors
    "detect_shot_cuts",
    "detect_speech_islands",
    "merge_speech_probabilities",
    "detect_cv_quality_events",
    "parse_blackdetect",
    "parse_freezedetect",
    "merge_blur_segments",
    "count_faces_in_image",
    "max_faces_in_frame_paths",
    "reset_detector_cache",
    "extract_frame_at_time",
    "extract_frames_for_times",
    "MotionGuard",
    # boundary / windows / report
    "snap_to_cuts",
    "apply_safety_inset",
    "has_internal_cut",
    "plan_windows",
    "build_quality_report",
    "merged_event_duration",
    # errors
    "AnnotationV4Error",
    "SchemaError",
    "SemanticError",
    "RuntimeVLMError",
    "UnrecoverableError",
]
