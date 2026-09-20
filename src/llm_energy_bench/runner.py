"""Experiment orchestration and derived request metrics.

The runner is deliberately small and sequential. It owns the boundary between
the independently tested Ollama, NVML, and artifact modules: preload and
placement checks happen before a run directory exists, while every measured
request is persisted before moving to the next one.
"""

from __future__ import annotations

import json
import platform
import random
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from llm_energy_bench.config import (
    ExperimentConfig,
    PromptCase,
    PromptCategory,
    load_prompts,
    prompts_fingerprint,
)
from llm_energy_bench.nvml import (
    EnergySource,
    GpuCapabilities,
    NvmlSampler,
    TelemetrySample,
)
from llm_energy_bench.ollama import InferenceRequest, InferenceResult, OllamaClient, RunningModel
from llm_energy_bench.results import (
    MANIFEST,
    OUTPUTS,
    REQUESTS,
    RESOLVED_CONFIG,
    TELEMETRY,
    VALIDATION,
    GzipJsonlWriter,
    JsonlWriter,
    RunStatus,
    assert_public_safe,
    create_run_dir,
    scan_for_private_data,
    sha256_file,
    validate_run,
    write_json,
    write_text,
)

MAX_TELEMETRY_GAP_S = 0.5
# Consumer drivers can expose a callable total-energy field whose values are
# nevertheless physically implausible. Keep this deliberately permissive: the
# check rejects broken counters, not ordinary sampling error around short peaks.
ENERGY_CONSISTENCY_FACTOR = 2.0
POWER_LIMIT_TOLERANCE = 1.2
JOULES_PER_KWH = 3_600_000.0
TOKENS_PER_MILLION = 1_000_000.0


class RunnerError(Exception):
    """Base error for experiment orchestration."""


class RunnerPreflightError(RunnerError):
    """The requested experiment cannot be measured reproducibly on this host."""


@dataclass(frozen=True, slots=True)
class RequestMetrics:
    """Derived metrics for one measured request.

    Raw Ollama counters and telemetry remain authoritative. These values can be
    regenerated, and every absent or invalid denominator stays ``None`` rather
    than being converted to a misleading numeric zero.
    """

    request_id: str
    prompt_id: str
    prompt_category: PromptCategory
    repetition: int
    valid: bool
    invalid_reasons: tuple[str, ...]
    latency_seconds: float
    ttft_seconds: float | None
    prompt_tokens: int | None
    cached_prompt_tokens: int | None
    output_tokens: int | None
    prefill_tokens_per_second: float | None
    decode_tokens_per_second: float | None
    end_to_end_tokens_per_second: float | None
    average_gpu_power_watts: float | None
    observed_peak_gpu_power_watts: float | None
    gpu_energy_joules: float | None
    joules_per_output_token: float | None
    output_tokens_per_joule: float | None
    gpu_cost_per_million_output_tokens: float | None
    cost_currency: str | None
    energy_source: EnergySource
    energy_fallback_reason: str | None
    telemetry_sample_count: int
    max_telemetry_gap_seconds: float | None
    temperature_start_c: int | None
    temperature_peak_c: int | None
    power_limit_watts: float | None
    vram_start_bytes: int | None
    vram_peak_bytes: int | None
    quality_score: float | None

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, StrEnum):
                value = value.value
            elif isinstance(value, tuple):
                value = list(value)
            record[item.name] = value
        return record


@dataclass(frozen=True, slots=True)
class _PlannedRequest:
    prompt: PromptCase
    repetition: int


def derive_request_metrics(
    result: InferenceResult,
    samples: tuple[TelemetrySample, ...],
    capabilities: GpuCapabilities,
    prompt: PromptCase,
    *,
    repetition: int,
    tariff_per_kwh: float | None = None,
    currency: str | None = None,
) -> RequestMetrics:
    """Derive one request's rates, energy, efficiency, and optional cost."""
    ordered = tuple(sorted(samples, key=lambda item: item.monotonic_s))
    reasons: list[str] = []

    if not result.valid:
        reasons.append(f"runtime:{_enum_value(result.invalid_kind) or 'invalid'}")
    if any(item.request_id != result.request_id for item in ordered):
        reasons.append("telemetry_request_id")

    max_gap = _max_gap(ordered)
    if len(ordered) < 2:
        reasons.append("telemetry_samples")
    elif max_gap is not None and max_gap > MAX_TELEMETRY_GAP_S:
        reasons.append("telemetry_gap")

    energy, average_power, peak_power, energy_source, fallback_reason = _energy_metrics(
        ordered, capabilities
    )
    if energy is None or energy <= 0:
        reasons.append("gpu_energy")

    output_tokens = result.eval_count
    if output_tokens is None or output_tokens <= 0:
        reasons.append("output_tokens")

    cached_tokens = result.prompt_eval_cached_count
    if cached_tokens is not None and cached_tokens > 0:
        reasons.append("cached_prompt_tokens")

    prompt_tokens = result.prompt_eval_count
    uncached_prompt_tokens = prompt_tokens
    if prompt_tokens is not None and cached_tokens is not None:
        uncached_prompt_tokens = prompt_tokens - cached_tokens
        if uncached_prompt_tokens < 0:
            reasons.append("cached_prompt_tokens_exceed_prompt_tokens")
            uncached_prompt_tokens = None

    prefill_rate = _rate(uncached_prompt_tokens, result.prompt_eval_duration_ns, 1e9)
    decode_rate = _rate(output_tokens, result.eval_duration_ns, 1e9)
    end_to_end_rate = _rate(output_tokens, result.latency_s, 1.0)
    joules_per_token = _ratio(energy, output_tokens)
    tokens_per_joule = _ratio(output_tokens, energy)

    cost = None
    if tariff_per_kwh is not None and currency is not None and joules_per_token is not None:
        cost = joules_per_token * TOKENS_PER_MILLION / JOULES_PER_KWH * tariff_per_kwh

    temperatures = _present(item.temperature_c for item in ordered)
    vram = _present(item.vram_used_bytes for item in ordered)
    power_limits = _present(item.power_limit_watts for item in ordered)

    quality_score = None
    if prompt.is_scored:
        quality_score = float(all(expected in result.text for expected in prompt.expect_contains))

    return RequestMetrics(
        request_id=result.request_id,
        prompt_id=prompt.prompt_id,
        prompt_category=prompt.category,
        repetition=repetition,
        valid=not reasons,
        invalid_reasons=tuple(dict.fromkeys(reasons)),
        latency_seconds=result.latency_s,
        ttft_seconds=result.ttft_s,
        prompt_tokens=prompt_tokens,
        cached_prompt_tokens=cached_tokens,
        output_tokens=output_tokens,
        prefill_tokens_per_second=prefill_rate,
        decode_tokens_per_second=decode_rate,
        end_to_end_tokens_per_second=end_to_end_rate,
        average_gpu_power_watts=average_power,
        observed_peak_gpu_power_watts=peak_power,
        gpu_energy_joules=energy,
        joules_per_output_token=joules_per_token,
        output_tokens_per_joule=tokens_per_joule,
        gpu_cost_per_million_output_tokens=cost,
        cost_currency=currency if cost is not None else None,
        energy_source=energy_source,
        energy_fallback_reason=fallback_reason,
        telemetry_sample_count=len(ordered),
        max_telemetry_gap_seconds=max_gap,
        temperature_start_c=temperatures[0] if temperatures else None,
        temperature_peak_c=max(temperatures) if temperatures else None,
        power_limit_watts=power_limits[0] if power_limits else capabilities.power_limit_watts,
        vram_start_bytes=vram[0] if vram else None,
        vram_peak_bytes=max(vram) if vram else None,
        quality_score=quality_score,
    )


def run_experiment(
    config: ExperimentConfig,
    *,
    client_factory: Callable[[str], Any] | None = None,
    sampler_factory: Callable[..., Any] | None = None,
) -> Path:
    """Run one warm, sequential Ollama experiment and return its run directory.

    Factories are injectable only to keep hardware-independent tests honest;
    normal callers use the one-argument public contract.
    """
    prompts = load_prompts(config.prompt_path)
    client_builder = client_factory or OllamaClient
    sampler_builder = sampler_factory or NvmlSampler

    with client_builder(config.ollama_url) as client, sampler_builder(
        gpu_index=config.gpu_index,
        interval_ms=config.telemetry_interval_ms,
    ) as sampler:
        runtime_version = client.version()
        capabilities = sampler.probe(config.gpu_index)
        if capabilities.energy_source is EnergySource.UNAVAILABLE:
            raise RunnerPreflightError(
                "GPU exposes neither a total-energy counter nor a usable power field"
            )

        load_options = _model_load_options(config)
        models = tuple(
            _preflight_model(client.preload(model, options=load_options), model)
            for model in config.models
        )

        run_dir = create_run_dir(config.output_dir, config.experiment_id, config.host_id)
        resolved_config = _resolved_config_toml(config, prompts_fingerprint(prompts))
        assert_public_safe(resolved_config)
        write_text(run_dir / RESOLVED_CONFIG, resolved_config)

        manifest = _initial_manifest(
            run_dir=run_dir,
            config=config,
            prompts=prompts,
            runtime_version=runtime_version,
            capabilities=capabilities,
            models=models,
        )
        _write_manifest(run_dir, manifest)

        try:
            _execute_requests(
                run_dir,
                config,
                prompts,
                client,
                sampler,
                capabilities,
                models,
                manifest,
            )
        except BaseException as error:
            manifest["status"] = (
                RunStatus.INTERRUPTED.value
                if isinstance(error, KeyboardInterrupt)
                else RunStatus.FAILED.value
            )
            manifest["ended_utc"] = datetime.now(UTC).isoformat()
            manifest["failure"] = _safe_error(error)
            manifest["artifact_sha256"] = _artifact_hashes(run_dir)
            _write_manifest(run_dir, manifest)
            raise

        manifest["status"] = RunStatus.COMPLETED.value
        manifest["ended_utc"] = datetime.now(UTC).isoformat()
        manifest["artifact_sha256"] = _artifact_hashes(run_dir)
        _write_manifest(run_dir, manifest)
        validation = validate_run(run_dir)
        write_json(run_dir / VALIDATION, validation.to_dict())
        return run_dir


def _preflight_model(model: RunningModel, requested_name: str) -> RunningModel:
    if model.fully_on_gpu is not True:
        fraction = "unknown" if model.gpu_fraction is None else f"{model.gpu_fraction:.3f}"
        raise RunnerPreflightError(
            f"model {requested_name!r} is not confirmed fully on GPU "
            f"(GPU fraction: {fraction})"
        )
    if not model.digest:
        raise RunnerPreflightError(f"model {requested_name!r} has no resolved digest")
    return model


def _execute_requests(
    run_dir: Path,
    config: ExperimentConfig,
    prompts: tuple[PromptCase, ...],
    client: Any,
    sampler: Any,
    capabilities: GpuCapabilities,
    preflight_models: tuple[RunningModel, ...],
    manifest: dict[str, Any],
) -> None:
    options = _request_options(config)
    with (
        JsonlWriter(run_dir / REQUESTS) as request_writer,
        JsonlWriter(run_dir / OUTPUTS) as output_writer,
        GzipJsonlWriter(run_dir / TELEMETRY) as telemetry_writer,
    ):
        measured_index = 0
        for model_index, (model_name, expected_model) in enumerate(
            zip(config.models, preflight_models, strict=True)
        ):
            active_model = _preflight_model(
                client.preload(model_name, options=_model_load_options(config)),
                model_name,
            )
            if active_model.digest != expected_model.digest:
                raise RunnerError(
                    f"model {model_name!r} digest changed after preflight: "
                    f"{expected_model.digest} -> {active_model.digest}"
                )

            for warmup_index in range(config.warmup_requests):
                prompt = prompts[warmup_index % len(prompts)]
                request_id = (
                    f"{run_dir.name}-warmup-m{model_index + 1}-w{warmup_index + 1}"
                )
                warmup = InferenceRequest(
                    request_id=request_id,
                    model=model_name,
                    prompt=_cache_busted_prompt(request_id, prompt.prompt),
                    options=options,
                )
                warmup_result = client.generate_stream(warmup)
                if not warmup_result.valid:
                    raise RunnerError(
                        f"warm-up {warmup_index + 1} for {model_name!r} failed: "
                        f"{warmup_result.invalid_reason or 'invalid result'}"
                    )
                manifest["completed_warmups"] += 1

            planned = [
                _PlannedRequest(prompt=prompt, repetition=repetition)
                for repetition in range(config.repetitions)
                for prompt in prompts
            ]
            random.Random(f"{config.order_seed}:{model_name}").shuffle(planned)

            for item in planned:
                measured_index += 1
                request_id = f"{run_dir.name}-request-{measured_index:05d}"
                request = InferenceRequest(
                    request_id=request_id,
                    model=model_name,
                    prompt=_cache_busted_prompt(request_id, item.prompt.prompt),
                    options=options,
                )
                request_record = {
                    **request.to_dict(),
                    "prompt_id": item.prompt.prompt_id,
                    "prompt_category": item.prompt.category.value,
                    "repetition": item.repetition,
                    "model_digest": active_model.digest,
                }
                assert_public_safe(request_record)
                request_writer.write(request_record)
                manifest["started_requests"] += 1

                samples: tuple[TelemetrySample, ...] = ()
                sampler.start(request_id)
                try:
                    inference = client.generate_stream(request)
                finally:
                    samples = sampler.stop()
                    for telemetry_sample in samples:
                        record = telemetry_sample.to_dict()
                        assert_public_safe(record)
                        telemetry_writer.write(record)

                metrics = derive_request_metrics(
                    inference,
                    samples,
                    capabilities,
                    item.prompt,
                    repetition=item.repetition,
                    tariff_per_kwh=config.tariff_per_kwh,
                    currency=config.currency,
                )
                output_record = {
                    **inference.to_dict(),
                    "runtime_valid": inference.valid,
                    "valid": metrics.valid,
                    "invalid_reasons": list(metrics.invalid_reasons),
                    "prompt_id": item.prompt.prompt_id,
                    "prompt_category": item.prompt.category.value,
                    "repetition": item.repetition,
                    "metrics": metrics.to_dict(),
                }
                assert_public_safe(output_record)
                output_writer.write(output_record)
                manifest["completed_requests"] += 1
                if metrics.valid:
                    manifest["valid_requests"] += 1


def _energy_metrics(
    samples: tuple[TelemetrySample, ...], capabilities: GpuCapabilities
) -> tuple[
    float | None,
    float | None,
    float | None,
    EnergySource,
    str | None,
]:
    elapsed = _sampled_elapsed(samples)
    counter_energy = _counter_delta(samples)
    instant_energy = _integrated_sample_power(samples, "power_instant_watts")
    legacy_energy = _integrated_sample_power(samples, "power_legacy_watts")
    source = capabilities.energy_source
    reason = capabilities.energy_fallback_reason

    if source is EnergySource.TOTAL_ENERGY_COUNTER:
        counter_problem = _counter_problem(
            counter_energy,
            elapsed,
            instant_energy if instant_energy is not None else legacy_energy,
            capabilities.power_limit_watts,
        )
        if counter_problem is None:
            energy = counter_energy
        elif instant_energy is not None:
            energy = instant_energy
            source = EnergySource.POWER_INSTANT_INTEGRATION
            reason = counter_problem + "; integrating instantaneous power instead"
        elif legacy_energy is not None:
            energy = legacy_energy
            source = EnergySource.POWER_LEGACY_INTEGRATION
            reason = counter_problem + "; integrating legacy power instead"
        else:
            energy = None
            source = EnergySource.UNAVAILABLE
            reason = counter_problem + "; no power fallback is available"
    elif source is EnergySource.POWER_INSTANT_INTEGRATION:
        if instant_energy is not None:
            energy = instant_energy
        elif legacy_energy is not None:
            energy = legacy_energy
            source = EnergySource.POWER_LEGACY_INTEGRATION
            reason = "instantaneous power samples are unusable; integrating legacy power"
        else:
            energy = None
            source = EnergySource.UNAVAILABLE
            reason = "instantaneous and legacy power samples are unusable"
    elif source is EnergySource.POWER_LEGACY_INTEGRATION:
        energy = legacy_energy
        if energy is None:
            source = EnergySource.UNAVAILABLE
            reason = "legacy power samples are unusable"
    else:
        energy = None

    power_values = _present(item.power_instant_watts for item in samples)
    if not power_values:
        power_values = _present(item.power_legacy_watts for item in samples)
    peak = max(power_values) if power_values else None
    average = None
    if energy is not None and elapsed is not None and elapsed > 0:
        average = energy / elapsed
    return energy, average, peak, source, reason


def _sampled_elapsed(samples: tuple[TelemetrySample, ...]) -> float | None:
    if len(samples) < 2:
        return None
    elapsed = samples[-1].monotonic_s - samples[0].monotonic_s
    return elapsed if elapsed > 0 else None


def _counter_delta(samples: tuple[TelemetrySample, ...]) -> float | None:
    values = _present(item.total_energy_joules for item in samples)
    return values[-1] - values[0] if len(values) >= 2 else None


def _integrated_sample_power(
    samples: tuple[TelemetrySample, ...], field_name: str
) -> float | None:
    points = [
        (item.monotonic_s, value)
        for item in samples
        if (value := getattr(item, field_name)) is not None
    ]
    return _integrate_power(points)


def _counter_problem(
    counter_energy: float | None,
    elapsed: float | None,
    integrated_power_energy: float | None,
    power_limit_watts: float | None,
) -> str | None:
    if counter_energy is None or counter_energy <= 0:
        return "total-energy counter did not produce a positive delta"
    if elapsed is not None and power_limit_watts is not None:
        counter_average_power = counter_energy / elapsed
        if counter_average_power > power_limit_watts * POWER_LIMIT_TOLERANCE:
            return "total-energy counter implies power above the enforced limit"
    if integrated_power_energy is not None and integrated_power_energy > 0:
        ratio = counter_energy / integrated_power_energy
        lower = 1 / ENERGY_CONSISTENCY_FACTOR
        if not lower <= ratio <= ENERGY_CONSISTENCY_FACTOR:
            return "total-energy counter is inconsistent with integrated power"
    return None


def _integrate_power(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    energy = 0.0
    for (left_t, left_power), (right_t, right_power) in zip(
        points, points[1:], strict=False
    ):
        interval = right_t - left_t
        if interval <= 0:
            return None
        energy += interval * (left_power + right_power) / 2.0
    return energy


def _rate(count: int | None, duration: float | int | None, scale: float) -> float | None:
    if count is None or count < 0 or duration is None or duration <= 0:
        return None
    return count * scale / duration


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _max_gap(samples: tuple[TelemetrySample, ...]) -> float | None:
    if len(samples) < 2:
        return None
    return max(
        right.monotonic_s - left.monotonic_s
        for left, right in zip(samples, samples[1:], strict=False)
    )


def _present[T](values: Iterable[T | None]) -> list[T]:
    return [value for value in values if value is not None]


def _enum_value(value: StrEnum | None) -> str | None:
    return None if value is None else value.value


def _request_options(config: ExperimentConfig) -> dict[str, Any]:
    # Ollama documents KV cache type as a server-wide environment setting,
    # defaulting to f16. It is recorded but is not a /api/generate option.
    options = config.options.to_dict()
    options.pop("kv_cache", None)
    return {key: value for key, value in options.items() if value is not None}


def _model_load_options(config: ExperimentConfig) -> dict[str, int]:
    return {
        "num_ctx": config.options.num_ctx,
        "num_gpu": config.options.num_gpu,
    }


def _cache_busted_prompt(request_id: str, prompt: str) -> str:
    return f"[llm-energy-bench:{request_id}]\n{prompt}"


def _initial_manifest(
    *,
    run_dir: Path,
    config: ExperimentConfig,
    prompts: tuple[PromptCase, ...],
    runtime_version: str,
    capabilities: GpuCapabilities,
    models: tuple[RunningModel, ...],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_dir.name,
        "status": RunStatus.RUNNING.value,
        "started_utc": datetime.now(UTC).isoformat(),
        "ended_utc": None,
        "experiment_id": config.experiment_id,
        "host_id": config.host_id,
        "git_commit": _git_commit(),
        "config_sha256": sha256_file(run_dir / RESOLVED_CONFIG),
        "prompt_set_sha256": prompts_fingerprint(prompts),
        "prompt_count": len(prompts),
        "repetitions": config.repetitions,
        "runtime": {"name": "ollama", "version": runtime_version},
        "gpu": capabilities.to_dict(),
        "models": [model.to_dict() for model in models],
        "controls": config.to_dict(),
        "host": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
        },
        "completed_warmups": 0,
        "started_requests": 0,
        "completed_requests": 0,
        "valid_requests": 0,
        "failure": None,
        "artifact_sha256": {},
    }


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    assert_public_safe(manifest)
    write_json(run_dir / MANIFEST, manifest)


def _artifact_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in (RESOLVED_CONFIG, REQUESTS, OUTPUTS, TELEMETRY):
        path = run_dir / name
        if path.is_file():
            hashes[name] = sha256_file(path)
    return hashes


def _safe_error(error: BaseException) -> dict[str, str]:
    detail = str(error).strip()
    if detail and scan_for_private_data(detail):
        detail = "<redacted>"
    return {"type": type(error).__name__, "message": detail}


def _git_commit() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def _resolved_config_toml(config: ExperimentConfig, prompt_hash: str) -> str:
    sections: tuple[tuple[str, tuple[tuple[str, Any], ...]], ...] = (
        (
            "experiment",
            (
                ("id", config.experiment_id),
                ("host_id", config.host_id),
                ("repetitions", config.repetitions),
                ("warmup_requests", config.warmup_requests),
                ("order_seed", config.order_seed),
            ),
        ),
        (
            "runtime",
            (("ollama_url", config.ollama_url), ("models", list(config.models))),
        ),
        (
            "gpu",
            (
                ("index", config.gpu_index),
                ("telemetry_interval_ms", config.telemetry_interval_ms),
            ),
        ),
        (
            "prompts",
            (("file", config.prompt_path.name), ("sha256", prompt_hash)),
        ),
        (
            "options",
            (
                ("num_ctx", config.options.num_ctx),
                ("num_gpu", config.options.num_gpu),
                ("temperature", config.options.temperature),
                ("seed", config.options.seed),
                ("num_predict", config.options.num_predict),
                ("kv_cache", config.options.kv_cache),
                ("concurrency", config.concurrency),
            ),
        ),
        (
            "cost",
            (
                ("tariff_per_kwh", config.tariff_per_kwh),
                ("currency", config.currency),
            ),
        ),
    )
    lines = ["# Resolved experiment controls; absolute paths are intentionally omitted."]
    for name, values in sections:
        present = tuple((key, value) for key, value in values if value is not None)
        if not present:
            continue
        lines.extend(("", f"[{name}]"))
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in present)
    return "\n".join(lines) + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")
