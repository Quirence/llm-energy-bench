"""Tests for the frozen power-quality-v2 analysis contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_energy_bench.config import HostRole, PromptCategory
from llm_energy_bench.power_quality import (
    ConditionAggregate,
    PowerQualityError,
    PowerQualitySample,
    aggregate_condition,
    analyze_power_quality,
    mark_frontier,
    write_power_quality_analysis,
)
from llm_energy_bench.results import (
    WARMUPS,
    GzipJsonlWriter,
    JsonlWriter,
    sha256_file,
    write_json,
    write_text,
)


def _write_synthetic_run(
    root: Path,
    *,
    host: str,
    role: HostRole,
    model: str,
    power: float,
    launch: int,
) -> Path:
    run_dir = root / f"{host}-{model}-p{power:g}-launch{launch}"
    run_dir.mkdir(parents=True)
    digest = f"digest-{model}"
    write_text(run_dir / "config.resolved.toml", '[experiment]\nid = "synthetic"\n')
    with JsonlWriter(run_dir / WARMUPS) as writer:
        for index, cached in enumerate((40, 21, 20, 21), start=1):
            writer.write(
                {
                    "request_id": f"w{index}",
                    "model": model,
                    "model_digest": digest,
                    "warmup_index": index,
                    "prompt_id": "short-01",
                    "valid": True,
                    "prompt_eval_count": 50,
                    "prompt_eval_cached_count": cached,
                    "load_duration_ns": 10_000_000,
                }
            )
    with JsonlWriter(run_dir / "requests.jsonl") as writer:
        writer.write({"request_id": "r0", "model_digest": digest})
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(
            {
                "request_id": "r0",
                "model": model,
                "model_digest": digest,
                "prompt_id": "short-01",
                "prompt_category": "short",
                "valid": True,
                "invalid_reasons": [],
                "latency_s": 2.0,
                "ttft_s": 0.2,
                "prompt_eval_count": 26,
                "prompt_eval_cached_count": 21,
                "eval_count": 100,
                "total_duration_ns": 2_000_000_000,
                "load_duration_ns": 10_000_000,
                "prompt_eval_duration_ns": 1_000_000_000,
                "eval_duration_ns": 1_000_000_000,
                "metrics": {
                    "gpu_energy_joules": power / 5,
                    "telemetry_sample_count": 2,
                    "max_telemetry_gap_seconds": 0.1,
                    "template_cache_baseline_tokens": 20,
                    "excess_cached_prompt_tokens": 1,
                    "uncached_prompt_tokens": 5,
                    "quality_score": None,
                },
            }
        )
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        for timestamp in (0.0, 0.1):
            writer.write(
                {
                    "request_id": "r0",
                    "monotonic_s": timestamp,
                    "power_limit_watts": power,
                }
            )

    study = {
        "protocol_id": "power-quality-v2",
        "host_role": role.value,
        "condition_id": f"{model}-p{power:g}",
        "launch_index": launch,
    }
    environment = {
        "idle_probe_seconds": 15.0,
        "max_gpu_utilization_p95_percent": 5.0,
        "max_start_temperature_c": 55,
        "max_idle_vram_used_mib": 512.0,
    }
    artifacts = (
        "config.resolved.toml",
        WARMUPS,
        "requests.jsonl",
        "outputs.jsonl",
        "telemetry.jsonl.gz",
    )
    manifest = {
        "schema_version": 3,
        "run_id": run_dir.name,
        "status": "completed",
        "host_id": host,
        "prompt_set_sha256": "frozen-prompt-hash",
        "runtime": {"name": "ollama", "version": "test"},
        "gpu": {
            "power_limit_watts": power,
            "power_limit_default_watts": max(power, 120.0),
            "power_limit_min_watts": 5.0,
            "power_limit_max_watts": 200.0,
        },
        "study": study,
        "environment_baseline": {
            "duration_seconds": 15.0,
            "sample_count": 151,
            "gpu_utilization_p95_percent": 0.0,
            "temperature_start_c": 40,
            "vram_used_peak_bytes": 128 * 1024**2,
            "problems": [],
        },
        "prompt_cache_policy": "template_floor_v2",
        "cache_buster_policy": "uuid_stable_slot_prefix_v4",
        "max_cache_excess_tokens": 1,
        "max_measured_load_duration_ns": 100_000_000,
        "prompt_count": 1,
        "repetitions": 1,
        "completed_warmups": 4,
        "started_requests": 1,
        "completed_requests": 1,
        "valid_requests": 1,
        "models": [
            {
                "name": model,
                "digest": digest,
                "fully_on_gpu": True,
                "template_cache_baseline_tokens": 20,
            }
        ],
        "controls": {
            "models": [model],
            "warmup_requests": 4,
            "repetitions": 1,
            "order_seed": 42,
            "concurrency": 1,
            "telemetry_interval_ms": 100,
            "options": {
                "num_ctx": 4096,
                "num_gpu": 999,
                "temperature": 0.0,
                "seed": 42,
                "num_predict": 256,
                "kv_cache": "f16",
            },
            "expected_runtime_version": "test",
            "expected_model_digests": {model: digest},
            "study": study,
            "expected_power_limit_watts": power,
            "power_limit_tolerance_watts": 1.0,
            "environment": environment,
        },
        "config_sha256": sha256_file(run_dir / "config.resolved.toml"),
        "artifact_sha256": {name: sha256_file(run_dir / name) for name in artifacts},
    }
    write_json(run_dir / "manifest.json", manifest)
    return run_dir


def synthetic_v2_matrix(
    tmp_path: Path,
    *,
    omit: tuple[str, str, float, int] | None = None,
) -> tuple[Path, ...]:
    """Create primary 2x2x3 and 2x4x3 grids plus an external 2x3x3 grid."""
    runs: list[Path] = []
    for host, role, powers in (
        ("rtx5060", HostRole.PRIMARY, (115.0, 80.0)),
        ("rtx4060ti", HostRole.PRIMARY, (120.0, 100.0, 80.0, 60.0)),
        ("gtx1080", HostRole.EXTERNAL, (180.0, 140.0, 100.0)),
    ):
        for model in ("llama3", "qwen3"):
            for power in powers:
                for launch in (1, 2, 3):
                    if (host, model, power, launch) == omit:
                        continue
                    runs.append(
                        _write_synthetic_run(
                            tmp_path,
                            host=host,
                            role=role,
                            model=model,
                            power=power,
                            launch=launch,
                        )
                    )
    return tuple(runs)


def samples(
    *,
    energy: tuple[float, ...] = (10.0, 20.0),
    latency: tuple[float, ...] = (1.0, 2.0),
    correct: tuple[float, ...] = (1.0, 0.0),
) -> tuple[PowerQualitySample, ...]:
    return tuple(
        PowerQualitySample(
            host_id="rtx5060",
            host_role=HostRole.PRIMARY,
            model="llama3",
            power_limit_watts=80.0,
            workload=PromptCategory.SCORED,
            launch_index=1,
            output_tokens=100,
            eval_duration_seconds=seconds,
            energy_joules=joules,
            latency_seconds=seconds,
            quality_score=score,
        )
        for joules, seconds, score in zip(energy, latency, correct, strict=True)
    )


FAST_HIGH_ENERGY = ConditionAggregate(
    "rtx5060",
    HostRole.PRIMARY,
    "fast",
    120.0,
    PromptCategory.SHORT,
    100.0,
    5.0,
    20.0,
    1.0,
    20.0,
    1.0,
)
SLOW_LOW_ENERGY = ConditionAggregate(
    "rtx5060",
    HostRole.PRIMARY,
    "efficient",
    80.0,
    PromptCategory.SHORT,
    80.0,
    10.0,
    10.0,
    1.0,
    10.0,
    1.2,
)
DOMINATED = ConditionAggregate(
    "rtx5060",
    HostRole.PRIMARY,
    "dominated",
    60.0,
    PromptCategory.SHORT,
    70.0,
    8.0,
    12.0,
    0.5,
    24.0,
    2.4,
)


def test_analysis_rejects_legacy_and_incomplete_matrix(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    write_json(legacy / "manifest.json", {"schema_version": 2})
    with pytest.raises(PowerQualityError, match="schema_version 3"):
        analyze_power_quality((legacy,), ("rtx5060", "rtx4060ti"), "gtx1080")

    runs = synthetic_v2_matrix(tmp_path / "incomplete", omit=("rtx4060ti", "qwen3", 120.0, 3))
    with pytest.raises(PowerQualityError, match="incomplete matrix"):
        analyze_power_quality(runs, ("rtx5060", "rtx4060ti"), "gtx1080")

    drifted = synthetic_v2_matrix(tmp_path / "drifted")
    manifest_path = drifted[0] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prompt_set_sha256"] = "different-prompt-hash"
    write_json(manifest_path, manifest)
    with pytest.raises(PowerQualityError, match="incompatible campaign controls"):
        analyze_power_quality(drifted, ("rtx5060", "rtx4060ti"), "gtx1080")


def test_energy_per_correct_uses_sums_and_zero_is_null() -> None:
    row = aggregate_condition(samples(energy=(10.0, 20.0), latency=(1.0, 2.0), correct=(1.0, 0.0)))
    assert row.energy_per_correct_joules == pytest.approx(30.0)
    assert row.latency_per_correct_seconds == pytest.approx(3.0)
    assert aggregate_condition(samples(correct=(0.0, 0.0))).energy_per_correct_joules is None


def test_external_gpu_is_not_pooled_with_primary_hosts(tmp_path: Path) -> None:
    result = analyze_power_quality(
        synthetic_v2_matrix(tmp_path), ("rtx5060", "rtx4060ti"), "gtx1080"
    )

    assert {row.host_role for row in result.rows} == {"primary", "external"}
    assert all(row.host_id != "gtx1080" for row in result.primary_comparisons)


def test_tradeoff_frontier_distinguishes_inversion_and_no_inversion() -> None:
    frontier = mark_frontier((FAST_HIGH_ENERGY, SLOW_LOW_ENERGY, DOMINATED))

    assert frontier == (FAST_HIGH_ENERGY, SLOW_LOW_ENERGY)


def test_analysis_artifacts_are_byte_deterministic(tmp_path: Path) -> None:
    analysis = analyze_power_quality(
        synthetic_v2_matrix(tmp_path / "runs"),
        ("rtx5060", "rtx4060ti"),
        "gtx1080",
    )

    first = write_power_quality_analysis(analysis, tmp_path / "first")
    second = write_power_quality_analysis(analysis, tmp_path / "second")

    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
