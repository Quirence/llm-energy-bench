"""Tests for the statistical rank-inversion criteria (Issue #6)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from llm_energy_bench.analysis import (
    BOOTSTRAP_ITERATIONS,
    MINIMUM_EFFECT,
    AnalysisError,
    BlockMeasurements,
    HypothesisOutcome,
    aggregate_ratio,
    blocks_from_records,
    bootstrap_relative_effect_ci,
    calibration_repeatability,
    evaluate_hypothesis,
    material_threshold,
    repeatability_cv,
)

FAST = 200  # bootstrap iterations for tests that do not check the default


def block(
    label: str,
    name: str,
    *,
    tokens: float,
    energy: float,
    latency: float,
    prompts: int = 3,
    repetitions: int = 2,
    quality: float | None = 1.0,
    jitter: float = 0.0,
) -> BlockMeasurements:
    """A block whose requests repeat, optionally with a linear spread across prompts."""
    steps = [1.0 + jitter * (i - (prompts - 1) / 2) for i in range(prompts)]
    return BlockMeasurements(
        label=label,
        block=name,
        prompts={
            f"p{index}": tuple((tokens, energy * step, latency * step) for _ in range(repetitions))
            for index, step in enumerate(steps)
        },
        quality_score=quality,
    )


def calibrated(names: list[str], cv: float = 0.0) -> dict[str, float]:
    return dict.fromkeys(names, cv)


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
    assert material_threshold(0.001) == pytest.approx(MINIMUM_EFFECT)


def test_the_material_threshold_is_three_times_the_cv_when_noise_dominates() -> None:
    assert material_threshold(0.10) == pytest.approx(0.30)
    assert material_threshold(0.04) == pytest.approx(0.12)


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def test_the_default_bootstrap_uses_ten_thousand_resamples() -> None:
    assert BOOTSTRAP_ITERATIONS == 10_000


def test_identical_samples_give_a_confidence_interval_containing_zero() -> None:
    samples = {f"p{i}": [(100.0, 2.0), (90.0, 2.0)] for i in range(4)}

    low, high = bootstrap_relative_effect_ci(samples, samples, iterations=FAST)

    assert low is not None and high is not None
    assert low <= 0.0 <= high


def test_clearly_separated_samples_give_an_interval_excluding_zero() -> None:
    fast = {f"p{i}": [(100.0, 1.0)] * 3 for i in range(4)}
    slow = {f"p{i}": [(40.0, 1.0)] * 3 for i in range(4)}

    low, high = bootstrap_relative_effect_ci(fast, slow, iterations=FAST)

    assert low == pytest.approx(1.5) and high == pytest.approx(1.5)


def test_the_bootstrap_resamples_shared_prompt_ids_first() -> None:
    """Prompt-level variance cancels when both configurations draw the same prompts.

    Both configurations are identical per prompt, but prompts differ tenfold.
    Resampling a flat request list independently per configuration would put
    that prompt-to-prompt spread into the interval; the hierarchical draw
    keeps the effect at exactly zero.
    """
    samples = {"cheap": [(10.0, 1.0)] * 3, "costly": [(1.0, 1.0)] * 3}

    low, high = bootstrap_relative_effect_ci(samples, dict(samples), iterations=FAST)

    assert low == pytest.approx(0.0) and high == pytest.approx(0.0)


def test_the_bootstrap_resamples_repetitions_within_a_prompt() -> None:
    """With one prompt, only the repetitions can move the interval."""
    noisy = {"only": [(8.0, 1.0), (12.0, 1.0)]}
    steady = {"only": [(10.0, 1.0), (10.0, 1.0)]}

    low, high = bootstrap_relative_effect_ci(noisy, steady, iterations=FAST)

    assert low is not None and high is not None
    assert low < 0.0 < high


def test_the_bootstrap_is_deterministic_for_a_given_seed() -> None:
    """A published interval must be reproducible from the raw data alone."""
    a = {"x": [(10.0, 1.0), (12.0, 1.0)], "y": [(9.0, 1.0), (11.0, 1.0)]}
    b = {"x": [(8.0, 1.0), (9.0, 1.0)], "y": [(7.0, 1.0), (8.5, 1.0)]}

    first = bootstrap_relative_effect_ci(a, b, seed=7, iterations=FAST)
    again = bootstrap_relative_effect_ci(a, b, seed=7, iterations=FAST)

    assert first == again
    assert all(value is not None for value in first)


def test_the_bootstrap_declines_to_answer_without_shared_prompts() -> None:
    assert bootstrap_relative_effect_ci({}, {"x": [(1.0, 1.0)]}) == (None, None)
    assert bootstrap_relative_effect_ci({"x": [(1.0, 1.0)]}, {"y": [(1.0, 1.0)]}) == (None, None)


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


def inverted_blocks(count: int, *, jitter: float = 0.0) -> list[BlockMeasurements]:
    blocks = []
    for index in range(count):
        name = f"block-{index}"
        blocks.append(
            block("fast-but-thirsty", name, tokens=200, energy=100.0, latency=1.0, jitter=jitter)
        )
        blocks.append(
            block("slow-but-frugal", name, tokens=100, energy=5.0, latency=4.0, jitter=jitter)
        )
    return blocks


def test_consistent_agreement_reports_the_hypothesis_as_unsupported() -> None:
    verdict = evaluate_hypothesis(agreeing_blocks(10), iterations=FAST)

    assert verdict.outcome is HypothesisOutcome.UNSUPPORTED
    assert verdict.agreement_rate == pytest.approx(1.0)
    assert verdict.material_inversions == ()
    assert "unsupported" in verdict.statement.lower()


def test_a_large_stable_inversion_blocks_the_unsupported_verdict() -> None:
    """One configuration wins on speed while another clearly wins on energy."""
    names = [f"block-{i}" for i in range(10)]

    verdict = evaluate_hypothesis(inverted_blocks(10), calibrated(names, 0.01), iterations=FAST)

    assert verdict.outcome is HypothesisOutcome.MATERIAL_INVERSION
    inversion = verdict.material_inversions[0]
    assert inversion.speed_winner == "fast-but-thirsty"
    assert inversion.energy_winner == "slow-but-frugal"
    assert inversion.threshold == pytest.approx(MINIMUM_EFFECT)
    assert inversion.relative_effect is not None and inversion.relative_effect > 0.05
    assert inversion.ci_low is not None and inversion.ci_low > 0


def test_an_uncalibrated_disagreement_is_never_material_or_unsupported() -> None:
    """Materiality waits for calibration data rather than assuming the 5% floor."""
    verdict = evaluate_hypothesis(inverted_blocks(1) + agreeing_blocks(0), iterations=FAST)

    assert verdict.material_inversions == ()
    assert verdict.inversions[0].threshold is None
    assert "calibration" in verdict.inversions[0].reason
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE


def test_one_uncalibrated_disagreement_keeps_high_agreement_inconclusive() -> None:
    blocks = agreeing_blocks(10)
    blocks += [
        block("fast-and-frugal", "odd", tokens=200, energy=100.0, latency=1.0),
        block("slow-and-thirsty", "odd", tokens=100, energy=5.0, latency=4.0),
    ]

    verdict = evaluate_hypothesis(blocks, iterations=FAST)

    assert verdict.agreement_rate == pytest.approx(10 / 11)
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE
    assert "odd" in verdict.statement


def test_a_disagreement_too_small_to_matter_is_not_a_material_inversion() -> None:
    """A 2% edge is below the 5% floor, so it does not overturn anything."""
    blocks = []
    names = [f"block-{i}" for i in range(10)]
    for name in names:
        blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("b", name, tokens=100, energy=9.8, latency=1.02))

    verdict = evaluate_hypothesis(blocks, calibrated(names), iterations=FAST)

    assert verdict.material_inversions == ()
    # "Unsupported" requires agreement in at least 90% of blocks. Here the
    # rankings disagree everywhere, if only by 2%, so the verdict is
    # inconclusive rather than unsupported.
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE
    assert verdict.agreement_rate == pytest.approx(0.0)


def test_poor_calibration_repeatability_raises_the_threshold() -> None:
    """A 15% effect is not material when calibration CV is 10%."""
    blocks = []
    names = [f"block-{i}" for i in range(10)]
    for name in names:
        blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("b", name, tokens=100, energy=8.5, latency=1.05))

    verdict = evaluate_hypothesis(blocks, calibrated(names, 0.10), iterations=FAST)

    assert verdict.inversions
    assert all(i.threshold == pytest.approx(0.30) for i in verdict.inversions)
    assert all(not i.material for i in verdict.inversions)


def test_agreement_below_ninety_percent_is_not_reported_as_unsupported() -> None:
    blocks = []
    names = [f"block-{i}" for i in range(10)]
    for index, name in enumerate(names):
        if index < 3:
            blocks.append(block("a", name, tokens=200, energy=100.0, latency=1.0))
            blocks.append(block("b", name, tokens=100, energy=5.0, latency=4.0))
        else:
            blocks.append(block("a", name, tokens=100, energy=10.0, latency=1.0))
            blocks.append(block("b", name, tokens=100, energy=40.0, latency=4.0))

    verdict = evaluate_hypothesis(blocks, calibrated(names), iterations=FAST)

    assert verdict.agreement_rate == pytest.approx(0.7)
    assert verdict.outcome is not HypothesisOutcome.UNSUPPORTED


def test_configurations_below_the_quality_floor_are_excluded() -> None:
    blocks = []
    for index in range(10):
        name = f"block-{index}"
        blocks.append(block("eligible", name, tokens=100, energy=10.0, latency=1.0))
        blocks.append(block("careless", name, tokens=500, energy=1.0, latency=0.1, quality=0.40))

    verdict = evaluate_hypothesis(blocks, iterations=FAST)

    assert verdict.excluded == ("careless",)
    assert "careless" not in verdict.configurations, "an ineligible configuration is never ranked"
    assert verdict.inversions == ()
    assert verdict.outcome is HypothesisOutcome.INCONCLUSIVE, "one configuration cannot be ranked"
    assert "careless" in verdict.statement, "but the exclusion is stated, not hidden"


def test_a_configuration_without_any_quality_score_is_not_ranked() -> None:
    blocks = [
        block("scored", "b", tokens=100, energy=10.0, latency=1.0),
        block("unscored", "b", tokens=100, energy=1.0, latency=0.1, quality=None),
    ]

    verdict = evaluate_hypothesis(blocks, iterations=FAST)

    assert verdict.excluded == ("unscored",)


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
    names = [f"block-{i}" for i in range(4)]
    first = evaluate_hypothesis(inverted_blocks(4), calibrated(names), iterations=FAST)
    again = evaluate_hypothesis(inverted_blocks(4), calibrated(names), iterations=FAST)

    assert json.loads(json.dumps(first.to_dict())) == json.loads(json.dumps(again.to_dict()))


def test_the_verdict_states_the_nvml_only_limitation() -> None:
    verdict = evaluate_hypothesis(agreeing_blocks(6), iterations=FAST)

    assert "GPU-only" in verdict.limitations
    assert "wall" in verdict.limitations.lower()


def test_the_markdown_rendering_names_both_rankings_and_the_protocol() -> None:
    verdict = evaluate_hypothesis(inverted_blocks(2), iterations=FAST)
    rendered = verdict.render()

    assert "speed" in rendered.lower()
    assert "energy" in rendered.lower()
    assert "95%" in rendered
    assert "10,000 resamples" in rendered
    assert "host x prompt category" in rendered


# --------------------------------------------------------------------------
# Bridge from run artifacts
# --------------------------------------------------------------------------


def manifest(run_id: str, host: str) -> dict[str, Any]:
    """The top-level manifest shape the runner writes."""
    return {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": "benchmark-v1",
        "host_id": host,
        "controls": {"experiment_id": "benchmark-v1", "repetitions": 3},
    }


def record(
    run_id: str,
    model: str,
    prompt: str,
    category: str,
    *,
    repetition: int = 0,
    tokens: float = 100.0,
    energy: float = 10.0,
    latency: float = 1.0,
    quality: float | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model": model,
        "prompt_id": prompt,
        "prompt_category": category,
        "repetition": repetition,
        "valid": True,
        "metrics": {
            "prompt_id": prompt,
            "prompt_category": category,
            "repetition": repetition,
            "output_tokens": tokens,
            "gpu_energy_joules": energy,
            "latency_seconds": latency,
            "quality_score": quality,
        },
    }


def test_blocks_read_the_host_from_the_top_level_manifest() -> None:
    manifests = {"run-1": manifest("run-1", "rtx5060")}
    blocks = blocks_from_records(
        [record("run-1", "m", "s1", "short"), record("run-1", "m", "q1", "scored", quality=1.0)],
        manifests,
    )

    assert {b.block for b in blocks} == {"rtx5060 / short", "rtx5060 / scored"}
    assert {b.label for b in blocks} == {"rtx5060 / m"}


def test_a_missing_manifest_host_is_an_error_not_a_silent_fallback() -> None:
    nested = {"run-1": {"run_id": "run-1", "config": {"host_id": "rtx5060"}}}

    with pytest.raises(AnalysisError, match="host_id"):
        blocks_from_records([record("run-1", "m", "s1", "short")], nested)


def test_decision_blocks_are_host_by_category() -> None:
    """The same model on two hosts is two configurations in two blocks."""
    manifests = {"a": manifest("a", "host-a"), "b": manifest("b", "host-b")}
    records = [
        record("a", "m1", "s1", "short", quality=1.0),
        record("a", "m2", "s1", "short", quality=1.0),
        record("b", "m1", "s1", "short", quality=1.0),
    ]

    blocks = blocks_from_records(records, manifests)

    by_block: dict[str, set[str]] = {}
    for b in blocks:
        by_block.setdefault(b.block, set()).add(b.label)
    assert by_block == {
        "host-a / short": {"host-a / m1", "host-a / m2"},
        "host-b / short": {"host-b / m1"},
    }


def test_repetitions_are_grouped_under_their_prompt_id() -> None:
    manifests = {"r": manifest("r", "h")}
    records = [
        record("r", "m", prompt, "short", repetition=rep, tokens=10.0 * (rep + 1))
        for prompt in ("s1", "s2")
        for rep in range(3)
    ]

    (only,) = blocks_from_records(records, manifests)

    assert set(only.prompts) == {"s1", "s2"}
    assert [r[0] for r in only.prompts["s1"]] == [10.0, 20.0, 30.0]


def test_quality_weights_each_prompt_equally_after_repetitions() -> None:
    """Prompt a scores 3/4 over four repetitions, prompt b 1/1 once: mean 0.875, not 0.8."""
    manifests = {"r": manifest("r", "h")}
    records = [
        record("r", "m", "a", "scored", repetition=i, quality=score)
        for i, score in enumerate([1.0, 1.0, 1.0, 0.0])
    ] + [record("r", "m", "b", "scored", quality=1.0)]

    (only,) = blocks_from_records(records, manifests)

    assert only.quality_score == pytest.approx(0.875)


def test_quality_eligibility_applies_to_the_configuration_in_every_category() -> None:
    """Failing the scored prompts also removes the configuration from the short block."""
    manifests = {"r": manifest("r", "h")}
    records = [
        record("r", "careless", "q1", "scored", quality=0.0),
        record("r", "careless", "s1", "short", tokens=500.0, energy=1.0, latency=0.1),
        record("r", "careful", "q1", "scored", quality=1.0),
        record("r", "careful", "s1", "short"),
    ]

    blocks = blocks_from_records(records, manifests)
    short = {b.label: b for b in blocks if b.block == "h / short"}

    assert short["h / careless"].quality_score == pytest.approx(0.0)
    assert not short["h / careless"].eligible
    assert short["h / careful"].eligible
    verdict = evaluate_hypothesis(blocks, iterations=FAST)
    assert "h / careless" in verdict.excluded


def test_records_without_usable_measurements_are_skipped() -> None:
    manifests = {"r": manifest("r", "h")}
    records = [
        record("r", "m", "s1", "short", energy=0.0),
        record("r", "m", "s2", "short"),
        {"run_id": "r", "model": "m", "metrics": None},
    ]

    (only,) = blocks_from_records(records, manifests)

    assert set(only.prompts) == {"s2"}


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------


def calibration_runs(speeds: list[float], efficiencies: list[float]) -> tuple[list, dict]:
    """One run per value: 100 tokens at the given tok/s and tok/J."""
    records = []
    manifests = {}
    for index, (speed, efficiency) in enumerate(zip(speeds, efficiencies, strict=True)):
        run = f"cal-{index}"
        manifests[run] = manifest(run, "h")
        for prompt in ("s1", "s2"):
            records.append(
                record(
                    run,
                    "q4",
                    prompt,
                    "short",
                    tokens=50.0,
                    latency=50.0 / speed,
                    energy=50.0 / efficiency,
                )
            )
    return records, manifests


def test_calibration_cv_uses_run_level_aggregates_and_the_larger_metric() -> None:
    records, manifests = calibration_runs([100.0, 100.0, 100.0], [0.9, 1.0, 1.1])

    repeatability = calibration_repeatability(records, manifests)

    assert repeatability == {"h / short": pytest.approx(repeatability_cv([0.9, 1.0, 1.1]))}


def test_calibration_needs_three_independent_runs() -> None:
    records, manifests = calibration_runs([100.0, 110.0], [1.0, 1.1])

    assert calibration_repeatability(records, manifests) == {}


def test_within_run_request_spread_does_not_count_as_repeatability() -> None:
    """Identical run totals mean zero CV even if individual requests differ."""
    manifests = {f"cal-{i}": manifest(f"cal-{i}", "h") for i in range(3)}
    records = [
        r
        for i in range(3)
        for r in (
            record(f"cal-{i}", "q4", "s1", "short", tokens=10.0, energy=1.0, latency=1.0),
            record(f"cal-{i}", "q4", "s2", "short", tokens=190.0, energy=99.0, latency=9.0),
        )
    ]

    assert calibration_repeatability(records, manifests) == {"h / short": pytest.approx(0.0)}
