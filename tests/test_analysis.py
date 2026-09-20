"""Tests for the statistical rank-inversion criteria (Issue #6)."""

from __future__ import annotations

import pytest

from llm_energy_bench.analysis import (
    MINIMUM_EFFECT,
    BlockMeasurements,
    HypothesisOutcome,
    aggregate_ratio,
    bootstrap_ratio_difference_ci,
    evaluate_hypothesis,
    material_threshold,
    repeatability_cv,
)


def block(
    label: str,
    name: str,
    *,
    tokens: float,
    energy: float,
    latency: float,
    n: int = 6,
    quality: float | None = 1.0,
    jitter: float = 0.0,
) -> BlockMeasurements:
    """A block whose per-request values repeat, optionally with a linear spread."""
    steps = [1.0 + jitter * (i - (n - 1) / 2) for i in range(n)]
    return BlockMeasurements(
        label=label,
        block=name,
        output_tokens=tuple(tokens for _ in steps),
        energy_joules=tuple(energy * s for s in steps),
        latency_seconds=tuple(latency * s for s in steps),
        quality_score=quality,
    )


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


def test_aggregate_ratio_is_total_over_total() -> None:
    assert aggregate_ratio([10, 100], [1.0, 100.0]) == pytest.approx(110 / 101)
    assert aggregate_ratio([], []) is None
    assert aggregate_ratio([10], [0.0]) is None


def test_repeatability_cv_is_zero_for_identical_measurements() -> None:
    assert repeatability_cv([2.0, 2.0, 2.0]) == pytest.approx(0.0)


def test_repeatability_cv_grows_with_spread() -> None:
    tight = repeatability_cv([10.0, 10.1, 9.9])
    loose = repeatability_cv([10.0, 14.0, 6.0])

    assert tight is not None and loose is not None
    assert loose > tight


def test_repeatability_cv_needs_two_measurements() -> None:
    assert repeatability_cv([1.0]) is None
    assert repeatability_cv([]) is None


def test_the_material_threshold_never_drops_below_five_percent() -> None:
    """A perfectly repeatable measurement still needs a 5% effect to matter."""
    assert material_threshold(0.0) == pytest.approx(MINIMUM_EFFECT)
    assert material_threshold(None) == pytest.approx(MINIMUM_EFFECT)
    assert material_threshold(0.001) == pytest.approx(MINIMUM_EFFECT)


def test_the_material_threshold_is_three_times_the_cv_when_noise_dominates() -> None:
    assert material_threshold(0.10) == pytest.approx(0.30)
    assert material_threshold(0.04) == pytest.approx(0.12)


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def test_identical_samples_give_a_confidence_interval_containing_zero() -> None:
    values = [100.0] * 8
    denominators = [2.0] * 8

    low, high = bootstrap_ratio_difference_ci(values, denominators, values, denominators)

    assert low is not None and high is not None
    assert low <= 0.0 <= high


def test_clearly_separated_samples_give_an_interval_excluding_zero() -> None:
    fast = [100.0] * 8
    slow = [40.0] * 8
    one_second = [1.0] * 8

    low, high = bootstrap_ratio_difference_ci(fast, one_second, slow, one_second)

    assert low is not None and low > 0.0
    assert high is not None


def test_the_bootstrap_is_deterministic_for_a_given_seed() -> None:
    """A published interval must be reproducible from the raw data alone.

    Two seeds may legitimately agree: with few requests the resample space is
    small and the percentiles land on the same values. Determinism is the
    property that matters, so that is what is asserted.
    """
    a, b = [10.0, 12.0, 9.0, 11.0], [1.0, 1.0, 1.0, 1.0]
    c, d = [8.0, 9.0, 7.0, 8.5], [1.0, 1.0, 1.0, 1.0]

    first = bootstrap_ratio_difference_ci(a, b, c, d, seed=7)
    again = bootstrap_ratio_difference_ci(a, b, c, d, seed=7)

    assert first == again
    assert all(value is not None for value in first)


def test_the_bootstrap_declines_to_answer_without_data() -> None:
    assert bootstrap_ratio_difference_ci([], [], [1.0], [1.0]) == (None, None)
    assert bootstrap_ratio_difference_ci([1.0], [0.0], [1.0], [1.0]) == (None, None)


# --------------------------------------------------------------------------
# The hypothesis
# --------------------------------------------------------------------------


def agreeing_blocks(count: int) -> list[BlockMeasurements]:
    """One configuration dominates both speed and energy in every block."""
    blocks = []
    for index in range(count):
        name = f"block-{index}"
        blocks.append(block("fast-and-frugal", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("slow-and-thirsty", name, tokens=100, energy=40.0, latency=4.0))
    return blocks


def test_consistent_agreement_reports_the_hypothesis_as_unsupported() -> None:
    verdict = evaluate_hypothesis(agreeing_blocks(10))

    assert verdict.outcome is HypothesisOutcome.UNSUPPORTED
    assert verdict.agreement_rate == pytest.approx(1.0)
    assert verdict.material_inversions == ()
    assert "unsupported" in verdict.statement.lower()


def test_a_large_stable_inversion_blocks_the_unsupported_verdict() -> None:
    """One configuration wins on speed while another clearly wins on energy."""
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        blocks.append(block("fast-but-thirsty", name, tokens=200, energy=100.0, latency=1.0))
        blocks.append(block("slow-but-frugal", name, tokens=100, energy=5.0, latency=4.0))

    verdict = evaluate_hypothesis(blocks)

    assert verdict.outcome is HypothesisOutcome.MATERIAL_INVERSION
    assert verdict.material_inversions
    inversion = verdict.material_inversions[0]
    assert inversion.speed_winner == "fast-but-thirsty"
    assert inversion.energy_winner == "slow-but-frugal"
    assert inversion.material is True
    assert inversion.relative_effect is not None and inversion.relative_effect > 0.05


def test_a_disagreement_too_small_to_matter_is_not_a_material_inversion() -> None:
    """A 2% edge is below the 5% floor, so it does not overturn anything."""
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("b", name, tokens=100, energy=9.8, latency=1.02))

    verdict = evaluate_hypothesis(blocks)

    assert verdict.material_inversions == ()
    # The pre-registered rule reports "unsupported" only when the two rankings
    # agree in at least 90% of blocks. Here they disagree everywhere, if only
    # by 2%, so the honest verdict is inconclusive rather than unsupported.
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE
    assert verdict.agreement_rate == pytest.approx(0.0)


def test_a_noisy_disagreement_is_not_material_even_when_large() -> None:
    """With poor repeatability the threshold rises to three times the CV."""
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0, jitter=0.30))
        blocks.append(block("b", name, tokens=100, energy=8.5, latency=1.05, jitter=0.30))

    verdict = evaluate_hypothesis(blocks)

    assert all(not i.material for i in verdict.inversions), "noise swamps a 15% effect"


def test_agreement_below_ninety_percent_is_not_reported_as_unsupported() -> None:
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        if index < 3:
            blocks.append(block("a", name, tokens=200, energy=100.0, latency=1.0))
            blocks.append(block("b", name, tokens=100, energy=5.0, latency=4.0))
        else:
            blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0))
            blocks.append(block("b", name, tokens=100, energy=40.0, latency=4.0))

    verdict = evaluate_hypothesis(blocks)

    assert verdict.agreement_rate == pytest.approx(0.7)
    assert verdict.outcome is not HypothesisOutcome.UNSUPPORTED


def test_configurations_below_the_quality_floor_are_excluded() -> None:
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        blocks.append(block("eligible", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("careless", name, tokens=500, energy=1.0, latency=0.1, quality=0.40))

    verdict = evaluate_hypothesis(blocks)

    assert verdict.excluded == ("careless",)
    assert "careless" not in verdict.configurations, "an ineligible configuration is never ranked"
    assert verdict.inversions == ()
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE, "one configuration cannot be ranked"
    assert "careless" in verdict.statement, "but the exclusion is stated, not hidden"


def test_a_single_configuration_cannot_be_compared() -> None:
    blocks = [block("only", f"block-{i}", tokens=100, energy=10.0, latency=1.0) for i in range(5)]

    verdict = evaluate_hypothesis(blocks)

    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE
    assert "one configuration" in verdict.statement.lower()


def test_no_blocks_at_all_is_inconclusive_not_a_crash() -> None:
    verdict = evaluate_hypothesis([])

    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE
    assert verdict.agreement_rate is None


def test_the_verdict_is_serializable_and_deterministic() -> None:
    import json

    first = evaluate_hypothesis(agreeing_blocks(6))
    again = evaluate_hypothesis(agreeing_blocks(6))

    assert json.loads(json.dumps(first.to_dict())) == json.loads(json.dumps(again.to_dict()))


def test_the_verdict_states_the_nvml_only_limitation() -> None:
    verdict = evaluate_hypothesis(agreeing_blocks(6))

    assert "GPU-only" in verdict.limitations
    assert "wall" in verdict.limitations.lower()


def test_the_markdown_rendering_names_both_rankings() -> None:
    verdict = evaluate_hypothesis(agreeing_blocks(6))
    rendered = verdict.render()

    assert "speed" in rendered.lower()
    assert "energy" in rendered.lower()
    assert "95%" in rendered
