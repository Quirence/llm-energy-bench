"""Tests for NVML capability probing and request-scoped telemetry sampling."""

from __future__ import annotations

import contextlib
import json
import threading
import time

import pytest

from fake_nvml import FULL_SUPPORT, FakeNvml
from llm_energy_bench.nvml import (
    EnergySource,
    NvmlNotSupported,
    NvmlSampler,
    NvmlUnavailable,
    PynvmlBinding,
    SamplerStateError,
)

# --------------------------------------------------------------------------
# Capability probing
# --------------------------------------------------------------------------


def test_probe_reports_full_support() -> None:
    sampler = NvmlSampler(binding=FakeNvml())
    caps = sampler.probe(0)

    assert caps.gpu_index == 0
    assert caps.name == "NVIDIA GeForce RTX 3050 Laptop GPU"
    assert caps.driver_version == "560.94"
    assert caps.vram_total_bytes == 4 * 1024**3
    assert caps.supports_total_energy is True
    assert caps.supports_power_instant is True
    assert caps.supports_power_legacy is True
    assert caps.power_limit_watts == pytest.approx(60.0)
    assert caps.field_errors == {}
    assert caps.unsupported_fields == ()


def test_probe_never_exposes_the_raw_gpu_uuid() -> None:
    fake = FakeNvml()
    caps = NvmlSampler(binding=fake).probe(0)

    fingerprint = caps.gpu_fingerprint
    assert fake.device_uuid not in fingerprint
    assert len(fingerprint) == 16
    assert int(fingerprint, 16) >= 0  # hex digest prefix


def test_probe_fingerprint_is_stable_and_distinguishes_gpus() -> None:
    first = NvmlSampler(binding=FakeNvml()).probe(0)
    same = NvmlSampler(binding=FakeNvml()).probe(0)
    other = NvmlSampler(binding=FakeNvml(device_uuid="GPU-aaaaaaaa")).probe(0)

    assert first.gpu_fingerprint == same.gpu_fingerprint
    assert first.gpu_fingerprint != other.gpu_fingerprint


def test_probe_marks_unsupported_fields_without_assuming_support() -> None:
    unsupported = tuple(f for f in FULL_SUPPORT if f not in {"total_energy_mj", "power_instant_mw"})
    caps = NvmlSampler(binding=FakeNvml(supported=unsupported)).probe(0)

    assert caps.supports_total_energy is False
    assert caps.supports_power_instant is False
    assert caps.supports_power_legacy is True
    # Unsupported is a fact about the hardware, not a failure to read it.
    assert caps.unsupported_fields == ("total_energy_mj", "power_instant_mw")
    assert caps.field_errors == {}


def test_probe_reports_null_power_limit_when_unsupported() -> None:
    unsupported = tuple(f for f in FULL_SUPPORT if f != "enforced_power_limit_mw")
    caps = NvmlSampler(binding=FakeNvml(supported=unsupported)).probe(0)

    assert caps.power_limit_watts is None  # unsupported is null, never zero
    assert caps.supports_power_limit is False
    assert "enforced_power_limit_mw" in caps.unsupported_fields


@pytest.mark.parametrize(
    ("unsupported", "expected_source"),
    [
        ((), EnergySource.TOTAL_ENERGY_COUNTER),
        (("total_energy_mj",), EnergySource.POWER_INSTANT_INTEGRATION),
        (("total_energy_mj", "power_instant_mw"), EnergySource.POWER_LEGACY_INTEGRATION),
        (("total_energy_mj", "power_instant_mw", "power_legacy_mw"), EnergySource.UNAVAILABLE),
    ],
)
def test_probe_selects_the_documented_energy_fallback_order(
    unsupported: tuple[str, ...], expected_source: EnergySource
) -> None:
    supported = tuple(f for f in FULL_SUPPORT if f not in unsupported)
    caps = NvmlSampler(binding=FakeNvml(supported=supported)).probe(0)

    assert caps.energy_source is expected_source
    if expected_source is EnergySource.TOTAL_ENERGY_COUNTER:
        assert caps.energy_fallback_reason is None
    else:
        assert caps.energy_fallback_reason


def test_probe_rejects_a_missing_gpu_index() -> None:
    sampler = NvmlSampler(binding=FakeNvml(device_count_value=1))
    with pytest.raises(NvmlUnavailable):
        sampler.probe(3)


def test_probe_reports_an_unavailable_nvml_library() -> None:
    sampler = NvmlSampler(binding=FakeNvml(available=False))
    with pytest.raises(NvmlUnavailable):
        sampler.probe(0)


def test_probe_initializes_and_shuts_nvml_down_exactly_once() -> None:
    fake = FakeNvml()
    NvmlSampler(binding=fake).probe(0)

    assert fake.init_calls == 1
    assert fake.shutdown_calls == 1


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------


def test_sampling_brackets_a_request_with_at_least_two_samples() -> None:
    with NvmlSampler(binding=FakeNvml(), gpu_index=0, interval_ms=1000) as sampler:
        sampler.start("req-1")
        samples = sampler.stop()

    assert len(samples) >= 2, "an opening and a closing sample must always exist"
    assert {s.request_id for s in samples} == {"req-1"}


def test_samples_carry_every_supported_field() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=1000) as sampler:
        sampler.start("req-1")
        sample = sampler.stop()[0]

    assert sample.power_instant_watts == pytest.approx(45.0)
    assert sample.power_legacy_watts == pytest.approx(44.5)
    assert sample.total_energy_joules is not None
    assert sample.temperature_c == 63
    assert sample.vram_used_bytes == 1 * 1024**3
    assert sample.gpu_utilization_percent == 97
    assert sample.memory_utilization_percent == 41
    assert sample.sm_clock_mhz == 1875
    assert sample.memory_clock_mhz == 6000
    assert sample.power_limit_watts == pytest.approx(60.0)
    assert sample.errors == {}


def test_samples_carry_both_monotonic_and_utc_timestamps() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=1000) as sampler:
        sampler.start("req-1")
        samples = sampler.stop()

    first, last = samples[0], samples[-1]
    assert last.monotonic_s >= first.monotonic_s
    assert first.utc.tzinfo is not None
    assert first.utc.isoformat().endswith("+00:00")


def test_the_sampler_keeps_running_at_the_configured_interval() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=10) as sampler:
        sampler.start("req-1")
        time.sleep(0.12)
        samples = sampler.stop()

    assert len(samples) >= 5


def test_unsupported_fields_are_null_and_never_zero() -> None:
    supported = tuple(f for f in FULL_SUPPORT if f not in {"total_energy_mj", "clocks_mhz"})
    with NvmlSampler(binding=FakeNvml(supported=supported), interval_ms=1000) as sampler:
        sampler.start("req-1")
        sample = sampler.stop()[0]

    assert sample.total_energy_joules is None
    assert sample.sm_clock_mhz is None
    assert sample.memory_clock_mhz is None
    assert sample.power_instant_watts == pytest.approx(45.0)


def test_a_field_error_is_recorded_per_field_without_losing_the_sample() -> None:
    fake = FakeNvml(raises={"temperature_c": RuntimeError("GPU is lost")})
    with NvmlSampler(binding=fake, interval_ms=1000) as sampler:
        sampler.start("req-1")
        sample = sampler.stop()[0]

    assert sample.temperature_c is None
    assert "GPU is lost" in sample.errors["temperature_c"]
    assert sample.power_instant_watts == pytest.approx(45.0), "other fields still collected"


def test_an_unsupported_field_is_not_reported_as_an_error() -> None:
    supported = tuple(f for f in FULL_SUPPORT if f != "total_energy_mj")
    with NvmlSampler(binding=FakeNvml(supported=supported), interval_ms=1000) as sampler:
        sampler.start("req-1")
        sample = sampler.stop()[0]

    assert sample.total_energy_joules is None
    assert "total_energy_mj" not in sample.errors


def test_a_sampling_exception_does_not_kill_the_sampler_thread() -> None:
    fake = FakeNvml(raises={"memory": RuntimeError("transient NVML failure")})
    with NvmlSampler(binding=fake, interval_ms=5) as sampler:
        sampler.start("req-1")
        time.sleep(0.05)
        samples = sampler.stop()

    assert len(samples) >= 3, "the thread survived repeated field failures"
    assert all(s.vram_used_bytes is None for s in samples)


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def test_repeated_start_is_rejected() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=1000) as sampler:
        sampler.start("req-1")
        with pytest.raises(SamplerStateError):
            sampler.start("req-2")
        sampler.stop()


def test_a_new_request_can_start_after_a_stop() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=1000) as sampler:
        sampler.start("req-1")
        first = sampler.stop()
        sampler.start("req-2")
        second = sampler.stop()

    assert {s.request_id for s in first} == {"req-1"}
    assert {s.request_id for s in second} == {"req-2"}


def test_stop_without_start_is_safe_and_returns_nothing() -> None:
    with NvmlSampler(binding=FakeNvml()) as sampler:
        assert sampler.stop() == ()


def test_stop_is_idempotent() -> None:
    with NvmlSampler(binding=FakeNvml(), interval_ms=1000) as sampler:
        sampler.start("req-1")
        samples = sampler.stop()
        assert sampler.stop() == ()

    assert len(samples) >= 2


def test_partial_samples_survive_an_interrupted_request() -> None:
    fake = FakeNvml()
    sampler = NvmlSampler(binding=fake, interval_ms=5)
    collected: tuple = ()
    with pytest.raises(KeyboardInterrupt):  # noqa: PT012 - the finally block is under test
        try:
            sampler.open()
            sampler.start("req-1")
            time.sleep(0.05)
            raise KeyboardInterrupt
        finally:
            collected = sampler.stop()
            sampler.close()

    assert len(collected) >= 3, "samples taken before the interrupt are preserved"
    assert fake.shutdown_calls == 1


def test_close_stops_a_running_sampler_thread() -> None:
    fake = FakeNvml()
    sampler = NvmlSampler(binding=fake, interval_ms=5)
    sampler.open()
    sampler.start("req-1")
    sampler.close()

    assert fake.shutdown_calls == 1
    assert not sampler.is_sampling
    running = {t.name for t in threading.enumerate()}
    assert not any(name.startswith("nvml-sampler") for name in running)


def test_close_is_idempotent() -> None:
    fake = FakeNvml()
    sampler = NvmlSampler(binding=fake)
    sampler.open()
    sampler.close()
    sampler.close()

    assert fake.shutdown_calls == 1


def test_start_without_open_is_rejected() -> None:
    sampler = NvmlSampler(binding=FakeNvml())
    with pytest.raises(SamplerStateError):
        sampler.start("req-1")


def test_the_default_interval_is_100_ms() -> None:
    assert NvmlSampler(binding=FakeNvml()).interval_ms == 100


def test_a_non_positive_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="interval_ms"):
        NvmlSampler(binding=FakeNvml(), interval_ms=0)


def test_the_real_binding_is_used_by_default_and_reports_absent_nvml() -> None:
    """On a host without an NVIDIA driver, probing fails cleanly."""
    sampler = NvmlSampler()
    assert isinstance(sampler._binding, PynvmlBinding)
    # Expected to fail on a driverless host such as CI; it must fail cleanly.
    with contextlib.suppress(NvmlUnavailable, NvmlNotSupported):
        sampler.probe(0)


def test_probe_records_a_genuine_read_failure_as_an_error() -> None:
    fake = FakeNvml(raises={"clocks_mhz": RuntimeError("driver timeout")})
    caps = NvmlSampler(binding=fake).probe(0)

    assert caps.supports_clocks is False
    assert "driver timeout" in caps.field_errors["clocks_mhz"]
    assert "clocks_mhz" not in caps.unsupported_fields


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def test_capabilities_serialize_to_json_without_the_gpu_uuid() -> None:
    fake = FakeNvml()
    payload = json.dumps(NvmlSampler(binding=fake).probe(0).to_dict())

    assert fake.device_uuid not in payload
    assert '"energy_source": "total_energy_counter"' in payload


def test_samples_serialize_to_json_with_null_for_unsupported_fields() -> None:
    supported = tuple(f for f in FULL_SUPPORT if f != "total_energy_mj")
    with NvmlSampler(binding=FakeNvml(supported=supported), interval_ms=1000) as sampler:
        sampler.start("req-1")
        sample = sampler.stop()[0]

    payload = json.loads(json.dumps(sample.to_dict()))
    assert payload["total_energy_joules"] is None
    assert payload["request_id"] == "req-1"
    assert payload["utc"].endswith("+00:00")
