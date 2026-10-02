"""Tests for fail-closed power-limit and idle-environment validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from llm_energy_bench.config import EnvironmentLimits
from llm_energy_bench.nvml import TelemetrySample

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def environment_sample(
    timestamp: float,
    *,
    utilization: int,
    temperature: int,
    power: float,
    vram: int,
    power_limit: float | None,
) -> TelemetrySample:
    return TelemetrySample(
        request_id="environment-preflight",
        monotonic_s=timestamp,
        utc=NOW,
        power_instant_watts=power,
        power_legacy_watts=power,
        total_energy_joules=100.0 + timestamp * power,
        temperature_c=temperature,
        vram_total_bytes=8 * 1024**3,
        vram_used_bytes=vram,
        gpu_utilization_percent=utilization,
        memory_utilization_percent=0,
        sm_clock_mhz=300,
        memory_clock_mhz=405,
        power_limit_watts=power_limit,
    )


BUSY_SAMPLES = (
    environment_sample(
        0.0,
        utilization=90,
        temperature=60,
        power=20.0,
        vram=600 * 1024**2,
        power_limit=80.0,
    ),
    environment_sample(
        1.0,
        utilization=95,
        temperature=61,
        power=25.0,
        vram=620 * 1024**2,
        power_limit=80.0,
    ),
)
POWER_CHANGED = (
    environment_sample(0.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=80.0),
    environment_sample(1.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=60.0),
)
POWER_MISSING = (
    environment_sample(0.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=None),
    environment_sample(1.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=None),
)


def test_expected_power_limit_mismatch_fails_closed() -> None:
    from llm_energy_bench.environment import (
        MeasurementEnvironmentError,
        ensure_expected_power_limit,
    )

    with pytest.raises(MeasurementEnvironmentError, match="80.0.*60.0"):
        ensure_expected_power_limit(
            observed_watts=60.0,
            expected_watts=80.0,
            tolerance_watts=1.0,
        )


def test_idle_baseline_rejects_busy_or_hot_gpu() -> None:
    from llm_energy_bench.environment import summarize_environment_samples

    baseline = summarize_environment_samples(BUSY_SAMPLES)
    problems = baseline.problems(EnvironmentLimits(15.0, 5.0, 55, 512.0))

    assert "gpu_utilization_p95" in problems
    assert "start_temperature" in problems
    assert "idle_vram" in problems


def test_request_power_limit_detects_change_and_missing_samples() -> None:
    from llm_energy_bench.environment import request_power_limit_problems

    assert request_power_limit_problems(POWER_CHANGED, 80.0, 1.0) == (
        "power_limit_mismatch",
        "power_limit_changed",
    )
    assert request_power_limit_problems(POWER_MISSING, 80.0, 1.0) == ("power_limit_missing",)
