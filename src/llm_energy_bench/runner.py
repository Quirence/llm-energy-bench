"""Preflight, measured execution, and the derived per-request metrics.

The runner is the only place where the Ollama client and the NVML sampler meet.
It is deliberately narrow: it decides what to measure and in what order, writes
every record the moment it exists, and computes derived numbers from raw data
it has already persisted.

Three rules govern it.

* Refuse rather than adapt. A missing model or a model partly resident in
  system memory stops the run. Measuring a workload other than the configured
  one would produce numbers that look valid and describe nothing.
* Never fabricate. Every derived value whose inputs are missing is ``None``.
  No ratio is computed over a zero or absent denominator.
* Keep what was measured. An interrupt or a crash finalizes the run with an
  explicit status and leaves every record already written in place.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from llm_energy_bench.config import ExperimentConfig, PromptCase, load_prompts, prompts_fingerprint
from llm_energy_bench.nvml import EnergySource, GpuCapabilities, TelemetrySample
from llm_energy_bench.ollama import (
    InferenceRequest,
    InferenceResult,
    ModelNotFound,
    OllamaError,
    RunningModel,
)
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
    validate_run,
    write_json,
    write_text,
)

# A model must be essentially fully resident: anything less means part of the
# workload ran on the CPU and the GPU figures describe a hybrid system.
MIN_GPU_RESIDENCY = 0.999

JOULES_PER_KWH = 3_600_000.0
MILLION = 1_000_000


class RunnerError(Exception):
    """The run could not be performed as configured."""


class PreflightFailed(RunnerError):
    """The host cannot produce a valid measurement, so nothing was measured."""


# --------------------------------------------------------------------------
# Injected collaborators
# --------------------------------------------------------------------------


class SupportsGeneration(Protocol):
    def version(self) -> str: ...
    def list_models(self) -> tuple[Any, ...]: ...
    def preload(self, model: str) -> RunningModel: ...
    def generate_stream(self, request: InferenceRequest) -> InferenceResult: ...
    def close(self) -> None: ...


class SupportsSampling(Protocol):
    def probe(self, gpu_index: int | None = ...) -> GpuCapabilities: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def start(self, request_id: str) -> None: ...
    def stop(self) -> tuple[TelemetrySample, ...]: ...


# --------------------------------------------------------------------------
# Derived metrics
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestMetrics:
    """Everything derived from one request and its telemetry window."""

    request_id: str
    prompt_id: str
    prompt_category: str
    repetition: int
    model: str
    model_digest: str | None
    cache_buster: str
    valid: bool
    invalid_kind: str | None
    invalid_reason: str | None
    quality_pass: bool | None

    latency_s: float
    ttft_s: float | None
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_eval_duration_ns: int | None
    eval_duration_ns: int | None

    prompt_tokens: int | None
    output_tokens: int | None
    prefix_cache_suspected: bool

    prefill_tokens_per_s: float | None
    decode_tokens_per_s: float | None
    end_to_end_tokens_per_s: float | None

    telemetry_samples: int
    average_power_watts: float | None
    max_power_watts: float | None
    energy_joules: float | None
    energy_source: str | None
    energy_note: str | None

    joules_per_output_token: float | None
    output_tokens_per_joule: float | None
    cost_per_million_output_tokens: float | None
    currency: str | None

    start_temperature_c: int | None
    max_temperature_c: int | None
    power_limit_watts: float | None
    start_vram_used_bytes: int | None
    peak_vram_used_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__slots__}


def score_output(prompt: PromptCase, text: str) -> bool | None:
    """Judge a scored prompt's answer, or return ``None`` for an unscored one.

    The check is deliberately mechanical: every expected fragment must appear,
    case-insensitively. Scoring happens while the prompt is in hand so that a
    run directory stays self-contained and a report never has to reach back to
    the prompt file that produced it.
    """
    if not prompt.is_scored:
        return None
    haystack = text.casefold()
    return all(fragment.casefold() in haystack for fragment in prompt.expect_contains)


def integrate_power(points: Sequence[tuple[float, float]]) -> float | None:
    """Integrate power over time with the trapezoidal rule.

    Returns ``None`` below two points: a single reading says what the power was
    at an instant, not how much energy a request spent.
    """
    if len(points) < 2:
        return None
    total = 0.0
    for (t0, p0), (t1, p1) in zip(points, points[1:], strict=False):
        span = t1 - t0
        if span > 0:
            total += (p0 + p1) / 2 * span
    return total


def compute_request_metrics(
    *,
    result: InferenceResult,
    samples: Sequence[TelemetrySample],
    caps: GpuCapabilities,
    tariff_per_kwh: float | None,
    currency: str | None,
    prompt: PromptCase | None = None,
    repetition: int = 1,
    cache_buster: str = "",
) -> RequestMetrics:
    """Derive one request's metrics from raw data that is already on disk."""
    output_tokens = result.eval_count
    prompt_tokens = result.prompt_eval_count

    energy, energy_source, energy_note = _energy(samples, caps)
    powers = [s for s in samples if _power_of(s) is not None]
    average_power = _mean([_power_of(s) for s in powers]) if powers else None
    max_power = max((_power_of(s) for s in powers), default=None)  # type: ignore[type-var]

    # A request that produced no tokens cannot support any per-token figure.
    usable_tokens = output_tokens if output_tokens and output_tokens > 0 else None
    joules_per_token = _divide(energy, usable_tokens)
    tokens_per_joule = _divide(usable_tokens, energy)

    temperatures = [s.temperature_c for s in samples if s.temperature_c is not None]
    vram = [s.vram_used_bytes for s in samples if s.vram_used_bytes is not None]
    limits = [s.power_limit_watts for s in samples if s.power_limit_watts is not None]

    return RequestMetrics(
        request_id=result.request_id,
        prompt_id=prompt.prompt_id if prompt else "",
        prompt_category=prompt.category.value if prompt else "",
        repetition=repetition,
        model=result.model,
        model_digest=result.model_digest,
        cache_buster=cache_buster,
        valid=result.valid and usable_tokens is not None,
        invalid_kind=result.invalid_kind.value if result.invalid_kind else None,
        invalid_reason=result.invalid_reason
        or (None if usable_tokens is not None else "no output tokens were reported"),
        quality_pass=score_output(prompt, result.text) if prompt else None,
        latency_s=result.latency_s,
        ttft_s=result.ttft_s,
        total_duration_ns=result.total_duration_ns,
        load_duration_ns=result.load_duration_ns,
        prompt_eval_duration_ns=result.prompt_eval_duration_ns,
        eval_duration_ns=result.eval_duration_ns,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        # Every measured prompt carries a unique prefix, so a missing or empty
        # prompt evaluation means the server reused a cache it should not have.
        prefix_cache_suspected=bool(cache_buster) and not prompt_tokens,
        prefill_tokens_per_s=_rate(prompt_tokens, result.prompt_eval_duration_ns),
        decode_tokens_per_s=_rate(output_tokens, result.eval_duration_ns),
        end_to_end_tokens_per_s=_divide(usable_tokens, result.latency_s),
        telemetry_samples=len(samples),
        average_power_watts=average_power,
        max_power_watts=max_power,
        energy_joules=energy,
        energy_source=energy_source.value if energy_source else None,
        energy_note=energy_note,
        joules_per_output_token=joules_per_token,
        output_tokens_per_joule=tokens_per_joule,
        cost_per_million_output_tokens=_cost(joules_per_token, tariff_per_kwh),
        currency=currency if tariff_per_kwh is not None else None,
        start_temperature_c=temperatures[0] if temperatures else None,
        max_temperature_c=max(temperatures) if temperatures else None,
        power_limit_watts=limits[0] if limits else None,
        start_vram_used_bytes=vram[0] if vram else None,
        peak_vram_used_bytes=max(vram) if vram else None,
    )


def _energy(
    samples: Sequence[TelemetrySample], caps: GpuCapabilities
) -> tuple[float | None, EnergySource | None, str | None]:
    """Measure the window's energy using the best source the GPU supports."""
    if len(samples) < 2:
        return None, None, "fewer than two telemetry samples in the request window"

    if caps.energy_source is EnergySource.TOTAL_ENERGY_COUNTER:
        readings = [s.total_energy_joules for s in samples if s.total_energy_joules is not None]
        if len(readings) >= 2:
            delta = readings[-1] - readings[0]
            if delta < 0:
                # A driver reload restarts the counter. Reporting the difference
                # would be negative energy; switching source mid-run would make
                # this request incomparable with its neighbours.
                return (
                    None,
                    None,
                    "the total-energy counter ran backwards during the request, "
                    "which usually means the driver reset; energy is not reported",
                )
            return delta, EnergySource.TOTAL_ENERGY_COUNTER, None

    points = [(s.monotonic_s, p) for s in samples if (p := _power_of(s)) is not None]
    energy = integrate_power(points)
    if energy is None:
        return None, None, "no usable power readings in the request window"

    source = (
        EnergySource.POWER_LEGACY_INTEGRATION
        if caps.energy_source is EnergySource.POWER_LEGACY_INTEGRATION
        else EnergySource.POWER_INSTANT_INTEGRATION
    )
    note = None
    if caps.energy_source is EnergySource.TOTAL_ENERGY_COUNTER:
        note = "the total-energy counter reported no usable readings; power was integrated"
    return energy, source, note


def _power_of(sample: TelemetrySample) -> float | None:
    """Prefer the unaveraged reading; fall back to the legacy averaged one."""
    if sample.power_instant_watts is not None:
        return sample.power_instant_watts
    return sample.power_legacy_watts


def _cost(joules_per_token: float | None, tariff_per_kwh: float | None) -> float | None:
    """GPU-only electricity cost of one million output tokens."""
    if joules_per_token is None or tariff_per_kwh is None:
        return None
    return joules_per_token * MILLION / JOULES_PER_KWH * tariff_per_kwh


def _rate(count: int | None, duration_ns: int | None) -> float | None:
    if count is None or duration_ns is None or duration_ns <= 0:
        return None
    return count / (duration_ns / 1e9)


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Unit:
    """One measured request: a prompt, a model, and which repetition it is."""

    model: str
    prompt: PromptCase
    repetition: int


def run_experiment(
    config: ExperimentConfig,
    *,
    client: SupportsGeneration | None = None,
    sampler: SupportsSampling | None = None,
) -> Path:
    """Execute one experiment and return its run directory.

    The directory is returned whatever the outcome; the manifest's status says
    how the run ended. Ctrl+C during a campaign means "stop measuring and keep
    the data", so it finalizes the run instead of propagating.
    """
    prompts = load_prompts(config.prompt_path)
    owns_client = client is None
    if client is None:
        from llm_energy_bench.ollama import OllamaClient

        client = OllamaClient(config.ollama_url)
    if sampler is None:
        from llm_energy_bench.nvml import NvmlSampler

        sampler = NvmlSampler(gpu_index=config.gpu_index, interval_ms=config.telemetry_interval_ms)

    try:
        sampler.open()
    except Exception as error:
        if owns_client:
            client.close()
        raise PreflightFailed(f"GPU telemetry is unavailable: {error}") from error

    try:
        caps = _preflight_gpu(sampler, config)
        placements = _preflight_models(client, config)
        return _execute(config, prompts, client, sampler, caps, placements)
    finally:
        sampler.close()
        if owns_client:
            client.close()


def _preflight_gpu(sampler: SupportsSampling, config: ExperimentConfig) -> GpuCapabilities:
    try:
        caps = sampler.probe(config.gpu_index)
    except Exception as error:
        raise PreflightFailed(f"the GPU could not be probed: {error}") from error

    if caps.energy_source is EnergySource.UNAVAILABLE:
        raise PreflightFailed(
            f"{caps.name} exposes no energy or power field, so energy cannot be measured; "
            "this host cannot produce a primary result"
        )
    return caps


def _preflight_models(
    client: SupportsGeneration, config: ExperimentConfig
) -> dict[str, RunningModel]:
    """Load every configured model and refuse anything short of full residency."""
    try:
        installed = {model.name for model in client.list_models()}
    except OllamaError as error:
        raise PreflightFailed(f"Ollama could not be queried: {error}") from error

    missing = [model for model in config.models if model not in installed]
    if missing:
        raise PreflightFailed(
            f"these models are not installed on this host: {', '.join(missing)}; "
            "pull them manually, since the bench never downloads a model"
        )

    placements: dict[str, RunningModel] = {}
    for model in config.models:
        try:
            running = client.preload(model)
        except (ModelNotFound, OllamaError) as error:
            raise PreflightFailed(f"{model} could not be loaded: {error}") from error

        fraction = running.gpu_fraction
        if fraction is None:
            raise PreflightFailed(
                f"{model}: Ollama did not report where the model is loaded, so GPU "
                "placement cannot be confirmed"
            )
        if fraction < MIN_GPU_RESIDENCY:
            raise PreflightFailed(
                f"{model} is only {fraction:.1%} resident in VRAM; partial CPU offload "
                "invalidates a primary GPU run"
            )
        placements[model] = running
    return placements


def _plan(config: ExperimentConfig, prompts: Sequence[PromptCase]) -> list[_Unit]:
    """Build the measured order.

    Repetitions are interleaved rather than grouped, so thermal drift spreads
    across every prompt instead of loading onto whichever one ran last.
    """
    units = [
        _Unit(model=model, prompt=prompt, repetition=repetition)
        for model in config.models
        for prompt in prompts
        for repetition in range(1, config.repetitions + 1)
    ]
    random.Random(config.order_seed).shuffle(units)
    return units


def _execute(
    config: ExperimentConfig,
    prompts: Sequence[PromptCase],
    client: SupportsGeneration,
    sampler: SupportsSampling,
    caps: GpuCapabilities,
    placements: dict[str, RunningModel],
) -> Path:
    run_dir = create_run_dir(config.output_dir, config.experiment_id, config.host_id)
    manifest = _manifest(config, prompts, caps, placements, client, run_dir)
    assert_public_safe(manifest)
    write_json(run_dir / MANIFEST, manifest)
    write_text(run_dir / RESOLVED_CONFIG, _resolved_config_text(config))

    status = RunStatus.FAILED
    failure: BaseException | None = None
    requests = JsonlWriter(run_dir / REQUESTS)
    outputs = JsonlWriter(run_dir / OUTPUTS)
    telemetry = GzipJsonlWriter(run_dir / TELEMETRY)

    try:
        _warm_up(config, prompts, client)
        for index, unit in enumerate(_plan(config, prompts), start=1):
            metrics, result, samples = _measure(config, unit, index, client, sampler, caps)
            requests.write(metrics.to_dict())
            outputs.write(
                {
                    "request_id": result.request_id,
                    "prompt_id": unit.prompt.prompt_id,
                    "model": unit.model,
                    "text": result.text,
                    "done_reason": result.done_reason,
                }
            )
            for telemetry_sample in samples:
                telemetry.write(telemetry_sample.to_dict())
        status = RunStatus.COMPLETED
    except KeyboardInterrupt:
        status = RunStatus.INTERRUPTED
    except BaseException as error:  # noqa: BLE001 - the status must survive any failure
        status = RunStatus.FAILED
        failure = error
    finally:
        requests.close()
        outputs.close()
        telemetry.close()
        _finalize(run_dir, manifest, status, failure)

    return run_dir


def _warm_up(
    config: ExperimentConfig, prompts: Sequence[PromptCase], client: SupportsGeneration
) -> None:
    """Run and discard the first requests, which measure loading, not generation."""
    for model in config.models:
        for index in range(config.warmup_requests):
            prompt = prompts[index % len(prompts)]
            client.generate_stream(
                InferenceRequest(
                    request_id=f"warmup-{model}-{index + 1}",
                    model=model,
                    prompt=_with_cache_buster(prompt.prompt, _nonce()),
                    options=_ollama_options(config),
                    keep_alive=-1,
                )
            )


def _measure(
    config: ExperimentConfig,
    unit: _Unit,
    index: int,
    client: SupportsGeneration,
    sampler: SupportsSampling,
    caps: GpuCapabilities,
) -> tuple[RequestMetrics, InferenceResult, tuple[TelemetrySample, ...]]:
    request_id = f"req-{index:04d}"
    cache_buster = _nonce()
    request = InferenceRequest(
        request_id=request_id,
        model=unit.model,
        prompt=_with_cache_buster(unit.prompt.prompt, cache_buster),
        options=_ollama_options(config),
        keep_alive=-1,
    )

    sampler.start(request_id)
    try:
        result = client.generate_stream(request)
    finally:
        # The sampler thread must stop even if generation raised, or the next
        # request would be measured against a window that never closed.
        samples = sampler.stop()

    metrics = compute_request_metrics(
        result=result,
        samples=samples,
        caps=caps,
        tariff_per_kwh=config.tariff_per_kwh,
        currency=config.currency,
        prompt=unit.prompt,
        repetition=unit.repetition,
        cache_buster=cache_buster,
    )
    return metrics, result, samples


def _nonce() -> str:
    return secrets.token_hex(8)


def _with_cache_buster(prompt: str, nonce: str) -> str:
    """Prefix a unique marker so the server cannot reuse a KV prefix cache.

    The marker leads the prompt on purpose: a shared prefix would let the
    server skip prefill and report a prefill time that measures nothing.
    """
    return f"[{nonce}]\n{prompt}"


def _ollama_options(config: ExperimentConfig) -> dict[str, Any]:
    options: dict[str, Any] = {
        "num_ctx": config.options.num_ctx,
        "temperature": config.options.temperature,
        "seed": config.options.seed,
    }
    if config.options.num_predict is not None:
        options["num_predict"] = config.options.num_predict
    return options


def _manifest(
    config: ExperimentConfig,
    prompts: Sequence[PromptCase],
    caps: GpuCapabilities,
    placements: dict[str, RunningModel],
    client: SupportsGeneration,
    run_dir: Path,
) -> dict[str, Any]:
    try:
        version = client.version()
    except OllamaError:
        version = "unknown"

    return {
        "run_id": run_dir.name,
        "status": RunStatus.RUNNING.value,
        "started_utc": datetime.now(UTC).isoformat(),
        "ended_utc": None,
        "config": config.to_dict(),
        "config_fingerprint": config.fingerprint(),
        "prompt_set_fingerprint": prompts_fingerprint(tuple(prompts)),
        "prompt_count": len(prompts),
        "gpu": caps.to_dict(),
        "runtime": {"name": "ollama", "ollama_version": version},
        "models": [placements[model].to_dict() for model in config.models],
        "failure": None,
    }


def _resolved_config_text(config: ExperimentConfig) -> str:
    """Re-emit the controls as TOML, without the paths that carry private data."""
    options = config.options
    return (
        "# Resolved controls for this run. Regenerated from the validated\n"
        "# configuration; paths are omitted because they carry private data.\n"
        "[experiment]\n"
        f'id = "{config.experiment_id}"\n'
        f'host_id = "{config.host_id}"\n'
        f"repetitions = {config.repetitions}\n"
        f"warmup_requests = {config.warmup_requests}\n"
        f"order_seed = {config.order_seed}\n"
        "\n[runtime]\n"
        f'ollama_url = "{config.ollama_url}"\n'
        f"models = [{', '.join(repr(m) for m in config.models)}]\n"
        "\n[gpu]\n"
        f"index = {config.gpu_index}\n"
        f"telemetry_interval_ms = {config.telemetry_interval_ms}\n"
        "\n[options]\n"
        f"num_ctx = {options.num_ctx}\n"
        f"temperature = {options.temperature}\n"
        f"seed = {options.seed}\n"
        f"num_predict = {options.num_predict}\n"
        f'kv_cache = "{options.kv_cache}"\n'
        f"concurrency = {config.concurrency}\n"
    ).replace("'", '"')


def _finalize(
    run_dir: Path, manifest: dict[str, Any], status: RunStatus, failure: BaseException | None
) -> None:
    """Close out the run, recording how it ended before anything else can fail."""
    manifest = dict(manifest)
    manifest["status"] = status.value
    manifest["ended_utc"] = datetime.now(UTC).isoformat()
    if failure is not None:
        manifest["failure"] = {"type": type(failure).__name__, "message": str(failure)[:500]}
    try:
        assert_public_safe(manifest)
    except Exception:
        manifest["failure"] = {"type": type(failure).__name__ if failure else "None", "message": ""}
    write_json(run_dir / MANIFEST, manifest)
    write_json(run_dir / VALIDATION, validate_run(run_dir).to_dict())
