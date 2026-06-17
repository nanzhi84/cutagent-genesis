"""Pure-logic tests for case_rubric_v1 (packages/creative/cases/rubric.py).

Covers score monotonicity, band thresholds, counts→canonical, ranking consistency,
fit_weights determinism, and the propose_bump anti-self-deception guardrail (a
candidate is proposed only when it reranks the calibration pool strictly more
accurately; nothing is proposed when the active card already ranks perfectly).
"""

from __future__ import annotations

from packages.core.config import build_settings
from packages.core.contracts import CaseRubric, CreativeFeatureVector, RubricDimension
from packages.creative.cases import metrics_import
from packages.creative.cases import rubric


def _features(hook: str, *, idx: int = 0, duration: float | None = None) -> CreativeFeatureVector:
    return CreativeFeatureVector(
        id=f"cfv_{hook}_{idx}",
        case_id="case_demo",
        hook_type=hook,
        cta_type="buy",
        script_structure="multi_beat",
        duration_sec=duration,
    )


def _settings():
    return build_settings().learning


# ---------------------------------------------------------------------------
# scoring + bands
# ---------------------------------------------------------------------------

def test_score_monotonicity_good_beats_bad():
    card = rubric.cold_start_rubric(rubric_id="rub_1", case_id="case_demo")
    good = CreativeFeatureVector(
        id="g",
        case_id="case_demo",
        hook_type="pain_point",
        cta_type="buy",
        script_structure="multi_beat",
        duration_sec=30.0,
    )
    bad = CreativeFeatureVector(
        id="b",
        case_id="case_demo",
        hook_type="statement",
        cta_type="follow",
        script_structure="single_beat",
        duration_sec=120.0,
    )
    good_composite, _ = rubric.composite_for(card, good)
    bad_composite, _ = rubric.composite_for(card, bad)
    assert good_composite > bad_composite
    assert 0.0 <= bad_composite <= 10.0
    assert 0.0 <= good_composite <= 10.0


def test_band_thresholds():
    assert rubric.band_for(8.0) == "top"
    assert rubric.band_for(rubric.BAND_TOP_MIN) == "top"
    assert rubric.band_for(6.0) == "ok"
    assert rubric.band_for(rubric.BAND_OK_MIN) == "ok"
    assert rubric.band_for(4.9) == "low"
    assert rubric.band_for(0.0) == "low"


def test_predict_is_blind_and_locks():
    card = rubric.cold_start_rubric(rubric_id="rub_1", case_id="case_demo")
    prediction = rubric.predict(
        card,
        _features("pain_point", duration=30.0),
        prediction_id="pred_1",
        case_id="case_demo",
        script_draft_id="draft_1",
    )
    assert prediction.script_draft_id == "draft_1"
    assert prediction.settled_reward is None
    assert prediction.band == rubric.band_for(prediction.composite)
    assert prediction.locked_at is not None


# ---------------------------------------------------------------------------
# counts_to_canonical
# ---------------------------------------------------------------------------

def test_counts_to_canonical_derives_rates_from_views():
    canonical = metrics_import.counts_to_canonical(
        {"views": 1000, "likes": 100, "comments": 50, "shares": 10, "follows": 5}
    )
    assert canonical["views"] == 1000
    assert canonical["like_rate"] == 0.1
    assert canonical["comment_rate"] == 0.05
    assert canonical["share_rate"] == 0.01
    assert canonical["follow_rate"] == 0.005


def test_counts_to_canonical_blank_views_no_rates():
    canonical = metrics_import.counts_to_canonical({"likes": 100})
    # No volume denominator → no rate fields fabricated.
    assert "like_rate" not in canonical


# ---------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------

def test_consistency_perfect_and_inverse():
    perfect = rubric.consistency([(1.0, 0.1), (2.0, 0.2), (3.0, 0.9)])
    assert perfect == 1.0
    inverse = rubric.consistency([(3.0, 0.1), (2.0, 0.2), (1.0, 0.9)])
    assert inverse == 0.0
    assert rubric.consistency([(1.0, 0.5)]) is None


# ---------------------------------------------------------------------------
# fit_weights determinism
# ---------------------------------------------------------------------------

def test_fit_weights_is_deterministic_and_normalized():
    base = [
        RubricDimension(key="hook_type", label="开场", weight=0.5, kind="categorical"),
        RubricDimension(key="cta_type", label="转化", weight=0.5, kind="categorical"),
    ]
    samples = [
        (_features("pain_point", idx=0), 0.9),
        (_features("pain_point", idx=1), 0.85),
        (_features("statement", idx=2), 0.1),
        (_features("statement", idx=3), 0.2),
    ]
    first = rubric.fit_weights(samples, base)
    second = rubric.fit_weights(samples, base)
    assert [d.model_dump() for d in first] == [d.model_dump() for d in second]
    total = sum(d.weight for d in first)
    assert abs(total - 1.0) < 1e-6
    # The categorical value scores become the mean reward of samples carrying them.
    hook = next(d for d in first if d.key == "hook_type")
    assert abs(hook.value_scores["pain_point"] - 0.875) < 1e-3
    assert abs(hook.value_scores["statement"] - 0.15) < 1e-3


# ---------------------------------------------------------------------------
# propose_bump guardrail
# ---------------------------------------------------------------------------

def _inverse_samples() -> list[tuple[CreativeFeatureVector, float]]:
    # pain_point → low reward; statement → high reward (so a card that ranks
    # pain_point HIGH is misranked and a refit must flip it).
    return [
        (_features("pain_point", idx=0), 0.1),
        (_features("pain_point", idx=1), 0.15),
        (_features("pain_point", idx=2), 0.2),
        (_features("statement", idx=3), 0.85),
        (_features("statement", idx=4), 0.9),
        (_features("statement", idx=5), 0.95),
    ]


def _single_hook_card(value_scores: dict[str, float]) -> CaseRubric:
    return CaseRubric(
        id="rub_active",
        case_id="case_demo",
        version=1,
        status="active",
        dimensions=[
            RubricDimension(
                key="hook_type",
                label="开场强度",
                weight=1.0,
                kind="categorical",
                value_scores=value_scores,
            )
        ],
        cold_start=True,
    )


def test_propose_bump_when_active_card_misranks():
    # WRONG card: ranks pain_point top although it actually performs worst.
    active = _single_hook_card({"pain_point": 1.0, "statement": 0.0})
    samples = _inverse_samples()
    proposal = rubric.propose_bump(
        active,
        samples,
        settings=_settings(),
        proposal_id="bump_1",
        candidate_id="rub_candidate",
    )
    assert proposal is not None
    assert proposal.new_consistency > proposal.old_consistency
    assert proposal.candidate.version == active.version + 1
    assert proposal.candidate.status == "draft"
    assert proposal.candidate.cold_start is False
    assert proposal.sample_size == len(samples)


def test_propose_bump_returns_none_when_already_perfect():
    # CORRECT card: already ranks statement above pain_point in line with reward.
    active = _single_hook_card({"pain_point": 0.1, "statement": 0.9})
    samples = _inverse_samples()
    assert rubric.consistency_for_rubric(active, samples) == 1.0
    proposal = rubric.propose_bump(
        active,
        samples,
        settings=_settings(),
        proposal_id="bump_1",
        candidate_id="rub_candidate",
    )
    assert proposal is None


def test_propose_bump_returns_none_below_min_samples():
    active = _single_hook_card({"pain_point": 1.0, "statement": 0.0})
    samples = _inverse_samples()[:2]
    proposal = rubric.propose_bump(
        active,
        samples,
        settings=_settings(),
        proposal_id="bump_1",
        candidate_id="rub_candidate",
    )
    assert proposal is None
