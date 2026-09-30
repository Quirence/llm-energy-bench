"""Tests for the preregistered, study-level statistical analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_energy_bench.analysis import (
    AnalysisError,
    HypothesisOutcome,
    RequestSample,
    aggregate_quality,
    analyze_study,
    assess_pairwise_inversion,
    coefficient_of_variation,
    material_effect_threshold,
)

ROOT = Path(__file__).parents[1]
RUNS = ROOT / "experiments" / "runs"
CALIBRATION_DIRS = tuple(
    RUNS / name
    for name in (
        "pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749",
        "pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922",
        "pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6",
        "pilot-v1-rtx4060ti-desktop-20260929T002903Z-552fa9",
        "pilot-v1-rtx4060ti-desktop-20260929T003009Z-f4bcf0",
        "pilot-v1-rtx4060ti-desktop-20260929T003046Z-9daa3d",
    )
)
BENCHMARK_DIRS = tuple(
    RUNS / name
    for name in (
        "benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3",
        "benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c",
    )
)
OBSERVATION_DIR = RUNS / "benchmark-v1-gtx1080-observation-20260929T114631Z-f56982"


def _sample(
    model: str,
    prompt_id: str,
    repetition: int,
    *,
    seconds: float,
    joules: float,
    quality: float | None = None,
) -> RequestSample:
    return RequestSample(
        model=model,
        model_digest=f"digest-{model}",
        category="scored" if quality is not None else "short",
        prompt_id=prompt_id,
        repetition=repetition,
        output_tokens=100,
        latency_seconds=seconds,
        gpu_energy_joules=joules,
        quality_score=quality,
    )


def test_sample_cv_and_material_floor_follow_the_frozen_rule() -> None:
    assert coefficient_of_variation((10.0, 12.0, 14.0)) == pytest.approx(2.0 / 12.0)
    assert material_effect_threshold(0.001, 0.002) == pytest.approx(0.05)
    assert material_effect_threshold(0.02, 0.04) == pytest.approx(0.12)


def test_quality_weights_prompts_equally_instead_of_requests() -> None:
    samples = tuple(
        [
            _sample("m", "one", repetition, seconds=1, joules=1, quality=1.0)
            for repetition in range(5)
        ]
        + [_sample("m", "two", 0, seconds=1, joules=1, quality=0.0)]
    )

    assert aggregate_quality(samples) == pytest.approx(0.5)


def test_paired_hierarchical_bootstrap_detects_a_material_inversion() -> None:
    fast = tuple(
        _sample("fast", prompt, repetition, seconds=1.0, joules=100.0)
        for prompt in ("p1", "p2")
        for repetition in range(3)
    )
    efficient = tuple(
        _sample("efficient", prompt, repetition, seconds=2.0, joules=50.0)
        for prompt in ("p1", "p2")
        for repetition in range(3)
    )

    result = assess_pairwise_inversion(
        host_id="host",
        category="short",
        first=fast,
        second=efficient,
        threshold=0.05,
        resamples=200,
        seed=42,
    )

    assert result is not None
    assert result.speed_winner == "fast"
    assert result.energy_winner == "efficient"
    assert result.speed_effect == pytest.approx(1.0)
    assert result.energy_effect == pytest.approx(1.0)
    assert result.speed_ci_low == pytest.approx(1.0)
    assert result.energy_ci_low == pytest.approx(1.0)
    assert result.material is True


def test_identical_rankings_are_not_reported_as_an_inversion() -> None:
    winner = tuple(
        _sample("winner", prompt, repetition, seconds=1.0, joules=50.0)
        for prompt in ("p1", "p2")
        for repetition in range(2)
    )
    loser = tuple(
        _sample("loser", prompt, repetition, seconds=2.0, joules=100.0)
        for prompt in ("p1", "p2")
        for repetition in range(2)
    )

    assert (
        assess_pairwise_inversion(
            host_id="host",
            category="short",
            first=winner,
            second=loser,
            threshold=0.05,
            resamples=20,
            seed=42,
        )
        is None
    )


def test_frozen_primary_dataset_yields_six_agreeing_blocks_and_host_local_exclusion() -> None:
    analysis = analyze_study(CALIBRATION_DIRS, BENCHMARK_DIRS, seed=42, resamples=100)

    assert analysis.outcome is HypothesisOutcome.NOT_SUPPORTED
    assert analysis.blocks_evaluated == 6
    assert analysis.blocks_agree == 6
    assert analysis.agreement_rate == pytest.approx(1.0)
    assert analysis.inversions == ()
    assert len(analysis.thresholds) == 6
    assert any(
        exclusion.host_id == "rtx4060ti-desktop"
        and exclusion.model == "llama3.2:3b-instruct-q8_0"
        and exclusion.quality_score == pytest.approx(0.725)
        for exclusion in analysis.exclusions
    )
    assert not any(
        exclusion.host_id == "maibenben-x16c" and exclusion.model == "llama3.2:3b-instruct-q8_0"
        for exclusion in analysis.exclusions
    )


def test_observation_run_cannot_enter_the_two_host_primary_verdict() -> None:
    with pytest.raises(AnalysisError, match="exactly two benchmark runs"):
        analyze_study(
            CALIBRATION_DIRS,
            (*BENCHMARK_DIRS, OBSERVATION_DIR),
            seed=42,
            resamples=10,
        )
