"""Fail-closed checks for the GPU state surrounding a measured run."""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from llm_energy_bench.config import EnvironmentLimits
from llm_energy_bench.nvml import NvmlSampler, TelemetrySample

MIB = 1024**2
ENVIRONMENT_REQUEST_ID = "environment-preflight"


class MeasurementEnvironmentError(Exception):
    """The host state cannot support a comparable power-quality measurement."""


@dataclass(frozen=True, slots=True)
class EnvironmentBaseline:
    """Aggregated idle GPU state recorded before any model is loaded."""

    duration_seconds: float
    sample_count: int
    gpu_utilization_mean_percent: float
    gpu_utilization_median_percent: float
    gpu_utilization_p95_percent: float
    power_mean_watts: float
    power_p95_watts: float
    temperature_start_c: int
    temperature_peak_c: int
    vram_used_peak_bytes: int

    def problems(self, limits: EnvironmentLimits) -> tuple[str, ...]:
        problems: list[str] = []
        if self.gpu_utilization_p95_percent > limits.max_gpu_utilization_p95_percent:
            problems.append("gpu_utilization_p95")
        if self.temperature_start_c > limits.max_start_temperature_c:
            problems.append("start_temperature")
        if self.vram_used_peak_bytes / MIB > limits.max_idle_vram_used_mib:
            problems.append("idle_vram")
        return tuple(problems)

    def to_dict(self, problems: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "sample_count": self.sample_count,
            "gpu_utilization_mean_percent": self.gpu_utilization_mean_percent,
            "gpu_utilization_median_percent": self.gpu_utilization_median_percent,
            "gpu_utilization_p95_percent": self.gpu_utilization_p95_percent,
            "power_mean_watts": self.power_mean_watts,
            "power_p95_watts": self.power_p95_watts,
            "temperature_start_c": self.temperature_start_c,
            "temperature_peak_c": self.temperature_peak_c,
            "vram_used_peak_bytes": self.vram_used_peak_bytes,
            "problems": list(problems),
        }


def ensure_expected_power_limit(
    observed_watts: float | None,
    expected_watts: float,
    tolerance_watts: float,
) -> None:
    """Reject a missing or mismatched enforced limit."""
    if observed_watts is None:
        raise MeasurementEnvironmentError(
            f"expected power limit {expected_watts:.1f} W but NVML reported no value"
        )
    if abs(observed_watts - expected_watts) > tolerance_watts:
        raise MeasurementEnvironmentError(
            f"expected power limit {expected_watts:.1f} W, observed {observed_watts:.1f} W"
        )


def capture_idle_baseline(
    sampler: NvmlSampler,
    limits: EnvironmentLimits,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> EnvironmentBaseline:
    """Sample an unloaded GPU for the configured idle window."""
    samples: tuple[TelemetrySample, ...] = ()
    sampler.start(ENVIRONMENT_REQUEST_ID)
    try:
        sleeper(limits.idle_probe_seconds)
    finally:
        samples = sampler.stop()
    return summarize_environment_samples(samples)


def summarize_environment_samples(
    samples: tuple[TelemetrySample, ...],
) -> EnvironmentBaseline:
    """Turn raw idle samples into a strict, public-safe baseline."""
    ordered = tuple(sorted(samples, key=lambda sample: sample.monotonic_s))
    if len(ordered) < 2:
        raise MeasurementEnvironmentError("idle baseline needs at least two telemetry samples")
    if any(sample.request_id != ENVIRONMENT_REQUEST_ID for sample in ordered):
        raise MeasurementEnvironmentError("idle baseline contains a different request id")

    utilization = _required_values(
        (sample.gpu_utilization_percent for sample in ordered),
        "GPU utilization",
    )
    temperature = _required_values(
        (sample.temperature_c for sample in ordered),
        "temperature",
    )
    vram = _required_values(
        (sample.vram_used_bytes for sample in ordered),
        "VRAM usage",
    )
    power = _complete_values(sample.power_instant_watts for sample in ordered)
    if power is None:
        power = _complete_values(sample.power_legacy_watts for sample in ordered)
    if power is None:
        raise MeasurementEnvironmentError("idle baseline has no complete power telemetry")

    duration = ordered[-1].monotonic_s - ordered[0].monotonic_s
    if duration <= 0:
        raise MeasurementEnvironmentError("idle baseline timestamps do not advance")
    return EnvironmentBaseline(
        duration_seconds=duration,
        sample_count=len(ordered),
        gpu_utilization_mean_percent=statistics.fmean(utilization),
        gpu_utilization_median_percent=statistics.median(utilization),
        gpu_utilization_p95_percent=_percentile(utilization, 0.95),
        power_mean_watts=statistics.fmean(power),
        power_p95_watts=_percentile(power, 0.95),
        temperature_start_c=int(temperature[0]),
        temperature_peak_c=int(max(temperature)),
        vram_used_peak_bytes=int(max(vram)),
    )


def request_power_limit_problems(
    samples: tuple[TelemetrySample, ...],
    expected_watts: float,
    tolerance_watts: float,
) -> tuple[str, ...]:
    """Describe missing, mismatched, or changing request-scoped power limits."""
    values = [sample.power_limit_watts for sample in samples]
    if not values or any(value is None for value in values):
        return ("power_limit_missing",)
    present = [float(value) for value in values if value is not None]
    problems: list[str] = []
    if any(abs(value - expected_watts) > tolerance_watts for value in present):
        problems.append("power_limit_mismatch")
    if max(present) - min(present) > tolerance_watts:
        problems.append("power_limit_changed")
    return tuple(problems)


def _required_values(values: Any, label: str) -> list[float]:
    complete = _complete_values(values)
    if complete is None:
        raise MeasurementEnvironmentError(f"idle baseline has incomplete {label} telemetry")
    return complete


def _complete_values(values: Any) -> list[float] | None:
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return [float(value) for value in collected]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
