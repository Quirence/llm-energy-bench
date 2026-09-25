"""Tests for experiment orchestration and derived request metrics."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from llm_energy_bench.config import (
    ExperimentConfig,
    InferenceOptions,
    PromptCase,
    PromptCategory,
)
from llm_energy_bench.nvml import (
    EnergySource,
    GpuCapabilities,
    TelemetrySample,
)
from llm_energy_bench.ollama import InferenceRequest, InferenceResult, RunningModel
from llm_energy_bench.results import read_gzip_jsonl, read_jsonl
from llm_energy_bench.runner import (
    RunnerError,
    RunnerPreflightError,
    _integrate_power,
    derive_request_metrics,
    run_experiment,
)

MODEL = "llama3.2:3b-instruct-q4_K_M"
DIGEST = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def make_config(
    tmp_path: Path,
    *,
    warmups: int = 2,
    repetitions: int = 2,
    tariff: float | None = None,
) -> ExperimentConfig:
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(
        "\n".join(
            (
                json.dumps(
                    {"id": "short-01", "category": "short", "prompt": "Say hello."}
                ),
                json.dumps(
                    {
                        "id": "scored-01",
                        "category": "scored",
                        "prompt": "What is two plus two?",
                        "expect_contains": ["4"],
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    source = tmp_path / "experiment.toml"
    source.write_text("# test config\n", encoding="utf-8")
    return ExperimentConfig(
        experiment_id="pilot",
        host_id="test-host",
        output_dir=tmp_path / "runs",
        ollama_url="http://ollama.test:11434",
        models=(MODEL,),
        prompt_path=prompts,
        gpu_index=0,
        telemetry_interval_ms=100,
        warmup_requests=warmups,
        repetitions=repetitions,
        order_seed=42,
        concurrency=1,
        options=InferenceOptions(
            num_ctx=4096,
            num_gpu=999,
            temperature=0.0,
            seed=42,
            num_predict=32,
            kv_cache="f16",
        ),
        tariff_per_kwh=tariff,
        currency="RUB" if tariff is not None else None,
        source_path=source,
    )


def capabilities(source: EnergySource = EnergySource.TOTAL_ENERGY_COUNTER) -> GpuCapabilities:
    return GpuCapabilities(
        gpu_index=0,
        name="Fake RTX",
        gpu_fingerprint="0123456789abcdef",
        driver_version="999.1",
        vram_total_bytes=8_000_000_000,
        supports_total_energy=source is EnergySource.TOTAL_ENERGY_COUNTER,
        supports_power_instant=source is not EnergySource.POWER_LEGACY_INTEGRATION,
        supports_power_legacy=True,
        supports_temperature=True,
        supports_utilization=True,
        supports_clocks=True,
        supports_power_limit=True,
        power_limit_watts=80.0,
        energy_source=source,
        energy_fallback_reason=None,
    )


def sample(
    request_id: str,
    timestamp: float,
    *,
    energy_j: float | None,
    instant_w: float | None,
    legacy_w: float | None = 11.0,
) -> TelemetrySample:
    return TelemetrySample(
        request_id=request_id,
        monotonic_s=timestamp,
        utc=NOW,
        power_instant_watts=instant_w,
        power_legacy_watts=legacy_w,
        total_energy_joules=energy_j,
        temperature_c=60 + int(timestamp),
        vram_total_bytes=8_000_000_000,
        vram_used_bytes=3_000_000_000 + int(timestamp * 1_000),
        gpu_utilization_percent=90,
        memory_utilization_percent=70,
        sm_clock_mhz=2_000,
        memory_clock_mhz=8_000,
        power_limit_watts=80.0,
    )


def result(
    request_id: str = "request-1",
    *,
    cached_tokens: int | None = 0,
    output_tokens: int = 4,
    valid: bool = True,
) -> InferenceResult:
    return InferenceResult(
        request_id=request_id,
        model=MODEL,
        model_digest=DIGEST,
        started_utc=NOW,
        ended_utc=NOW,
        t_start_s=10.0,
        t_first_chunk_s=10.1,
        t_first_token_s=10.2,
        t_end_s=12.0,
        ttft_s=0.2,
        latency_s=2.0,
        text="4",
        chunk_count=2,
        done=True,
        done_reason="stop",
        http_status=200,
        prompt_eval_count=26,
        prompt_eval_cached_count=cached_tokens,
        eval_count=output_tokens,
        total_duration_ns=2_000_000_000,
        load_duration_ns=10_000_000,
        prompt_eval_duration_ns=2_000_000_000,
        eval_duration_ns=1_000_000_000,
        valid=valid,
        invalid_kind=None,
        invalid_reason=None,
    )


class FakeClient:
    def __init__(
        self,
        *,
        fully_on_gpu: bool | None = True,
        interrupt_at: int | None = None,
        cached_counts: tuple[int | None, ...] | None = None,
    ) -> None:
        self.fully_on_gpu = fully_on_gpu
        self.interrupt_at = interrupt_at
        self.cached_counts = cached_counts
        self.requests: list[InferenceRequest] = []
        self.preload_options: list[dict[str, Any] | None] = []
        self.closed = False

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def version(self) -> str:
        return "0.99.0-test"

    def preload(
        self, model: str, *, options: dict[str, Any] | None = None
    ) -> RunningModel:
        self.preload_options.append(options)
        size = 3_000_000_000
        size_vram = (
            None if self.fully_on_gpu is None else size if self.fully_on_gpu else size - 1
        )
        return RunningModel(
            name=model,
            model=model,
            digest=DIGEST,
            size_bytes=size,
            size_vram_bytes=size_vram,
            quantization="Q4_K_M",
            parameter_size="3.2B",
            family="llama",
            context_length=4096,
        )

    def generate_stream(self, request: InferenceRequest) -> InferenceResult:
        self.requests.append(request)
        if self.interrupt_at == len(self.requests):
            raise KeyboardInterrupt
        cached_tokens = 0
        if self.cached_counts is not None:
            cached_tokens = self.cached_counts[len(self.requests) - 1]
        return result(request.request_id, cached_tokens=cached_tokens)


class FakeSampler:
    def __init__(
        self,
        source: EnergySource = EnergySource.TOTAL_ENERGY_COUNTER,
    ) -> None:
        self.capabilities = capabilities(source)
        self.started: list[str] = []
        self.stopped = 0
        self.closed = False
        self._request_id: str | None = None

    def __enter__(self) -> FakeSampler:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def probe(self, _gpu_index: int | None = None) -> GpuCapabilities:
        return self.capabilities

    def start(self, request_id: str) -> None:
        self._request_id = request_id
        self.started.append(request_id)

    def stop(self) -> tuple[TelemetrySample, ...]:
        self.stopped += 1
        if self._request_id is None:
            return ()
        request_id = self._request_id
        self._request_id = None
        return (
            sample(request_id, 0.0, energy_j=0.0, instant_w=10.0),
            sample(request_id, 0.1, energy_j=1.2, instant_w=14.0),
        )


def prompt() -> PromptCase:
    return PromptCase("scored-01", PromptCategory.SCORED, "2+2?", ("4",))


def test_total_energy_counter_takes_precedence_over_power_integration() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
        sample("request-1", 1.0, energy_j=112.0, instant_w=14.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=0,
    )

    assert metrics.energy_source is EnergySource.TOTAL_ENERGY_COUNTER
    assert metrics.gpu_energy_joules == pytest.approx(12.0)
    assert metrics.average_gpu_power_watts == pytest.approx(12.0)
    assert metrics.observed_peak_gpu_power_watts == pytest.approx(14.0)


def test_implausible_energy_counter_falls_back_to_power_integration() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
        sample("request-1", 1.0, energy_j=300.0, instant_w=14.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=0,
    )

    assert metrics.energy_source is EnergySource.POWER_INSTANT_INTEGRATION
    assert metrics.gpu_energy_joules == pytest.approx(12.0)
    assert metrics.energy_fallback_reason is not None
    assert "counter" in metrics.energy_fallback_reason


def test_instantaneous_power_uses_trapezoidal_integration() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=None, instant_w=10.0),
        sample("request-1", 1.0, energy_j=None, instant_w=14.0),
        sample("request-1", 3.0, energy_j=None, instant_w=18.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=0,
    )

    assert metrics.gpu_energy_joules == pytest.approx(44.0)
    assert metrics.average_gpu_power_watts == pytest.approx(44.0 / 3.0)
    assert metrics.observed_peak_gpu_power_watts == pytest.approx(18.0)


def test_duplicate_timestamp_uses_the_latest_reading_without_losing_energy() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=None, instant_w=10.0),
        sample("request-1", 0.1, energy_j=None, instant_w=14.0),
        sample("request-1", 0.1, energy_j=None, instant_w=16.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        prompt(),
        repetition=0,
    )

    assert metrics.energy_source is EnergySource.POWER_INSTANT_INTEGRATION
    assert metrics.gpu_energy_joules == pytest.approx(1.3)
    assert metrics.average_gpu_power_watts == pytest.approx(13.0)


def test_power_integration_rejects_decreasing_timestamps() -> None:
    assert _integrate_power([(0.1, 10.0), (0.0, 12.0)]) is None


def test_implausible_instant_power_falls_back_to_legacy_power() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=None, instant_w=9.0, legacy_w=8.0),
        sample("request-1", 0.1, energy_j=None, instant_w=4_666.0, legacy_w=12.0),
        sample("request-1", 0.2, energy_j=None, instant_w=10.0, legacy_w=16.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        prompt(),
        repetition=0,
    )

    assert metrics.energy_source is EnergySource.POWER_LEGACY_INTEGRATION
    assert metrics.gpu_energy_joules == pytest.approx(2.4)
    assert metrics.average_gpu_power_watts == pytest.approx(12.0)
    assert metrics.observed_peak_gpu_power_watts == pytest.approx(16.0)
    assert metrics.energy_fallback_reason is not None
    assert "enforced power limit" in metrics.energy_fallback_reason


def test_all_implausible_power_sources_make_energy_unavailable() -> None:
    samples = (
        sample("request-1", 0.0, energy_j=None, instant_w=9.0, legacy_w=8.0),
        sample("request-1", 0.1, energy_j=None, instant_w=4_666.0, legacy_w=4_000.0),
    )

    metrics = derive_request_metrics(
        result(),
        samples,
        capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        prompt(),
        repetition=0,
    )

    assert metrics.energy_source is EnergySource.UNAVAILABLE
    assert metrics.gpu_energy_joules is None
    assert metrics.average_gpu_power_watts is None
    assert metrics.observed_peak_gpu_power_watts is None
    assert "gpu_energy" in metrics.invalid_reasons
    assert metrics.energy_fallback_reason is not None
    assert "enforced power limit" in metrics.energy_fallback_reason


def test_efficiency_throughput_and_optional_cost_formulas() -> None:
    metrics = derive_request_metrics(
        result(),
        (
            sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
            sample("request-1", 1.0, energy_j=112.0, instant_w=14.0),
        ),
        capabilities(),
        prompt(),
        repetition=3,
        template_cache_baseline_tokens=0,
        tariff_per_kwh=0.2,
        currency="USD",
    )

    assert metrics.prefill_tokens_per_second == pytest.approx(13.0)
    assert metrics.decode_tokens_per_second == pytest.approx(4.0)
    assert metrics.end_to_end_tokens_per_second == pytest.approx(2.0)
    assert metrics.joules_per_output_token == pytest.approx(3.0)
    assert metrics.output_tokens_per_joule == pytest.approx(1 / 3)
    assert metrics.gpu_cost_per_million_output_tokens == pytest.approx(1 / 6)
    assert metrics.cost_currency == "USD"
    assert metrics.quality_score == 1.0
    assert metrics.repetition == 3


def test_cost_is_null_without_an_explicit_tariff() -> None:
    metrics = derive_request_metrics(
        result(),
        (
            sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
            sample("request-1", 1.0, energy_j=112.0, instant_w=14.0),
        ),
        capabilities(),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=0,
    )

    assert metrics.gpu_cost_per_million_output_tokens is None
    assert metrics.cost_currency is None


def test_cached_prompt_count_at_the_template_baseline_is_valid() -> None:
    metrics = derive_request_metrics(
        result(cached_tokens=20),
        (
            sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
            sample("request-1", 0.1, energy_j=101.2, instant_w=14.0),
        ),
        capabilities(),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=20,
    )

    assert metrics.valid is True
    assert metrics.template_cache_baseline_tokens == 20
    assert metrics.excess_cached_prompt_tokens == 0
    assert metrics.prefill_tokens_per_second == pytest.approx(3.0)


def test_cached_prompt_count_above_the_template_baseline_is_invalid() -> None:
    metrics = derive_request_metrics(
        result(cached_tokens=21),
        (
            sample("request-1", 0.0, energy_j=100.0, instant_w=10.0),
            sample("request-1", 1.0, energy_j=112.0, instant_w=14.0),
        ),
        capabilities(),
        prompt(),
        repetition=0,
        template_cache_baseline_tokens=20,
    )

    assert metrics.valid is False
    assert "cached_prompt_tokens_above_template_baseline" in metrics.invalid_reasons
    assert metrics.excess_cached_prompt_tokens == 1


def test_run_order_is_deterministic_and_warmups_are_excluded(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first_client = FakeClient()
    first_sampler = FakeSampler()

    first_dir = run_experiment(
        config,
        client_factory=lambda _url: first_client,
        sampler_factory=lambda **_kwargs: first_sampler,
    )
    first_requests = read_jsonl(first_dir / "requests.jsonl")

    second_client = FakeClient()
    second_sampler = FakeSampler()
    second_dir = run_experiment(
        config,
        client_factory=lambda _url: second_client,
        sampler_factory=lambda **_kwargs: second_sampler,
    )
    second_requests = read_jsonl(second_dir / "requests.jsonl")

    assert len(first_client.requests) == 6  # 2 warm-ups + 2 prompts x 2 repetitions
    assert len(first_requests) == 4
    assert len(read_jsonl(first_dir / "outputs.jsonl")) == 4
    assert len(read_gzip_jsonl(first_dir / "telemetry.jsonl.gz")) == 8
    assert [
        (record["prompt_id"], record["repetition"]) for record in first_requests
    ] == [
        (record["prompt_id"], record["repetition"]) for record in second_requests
    ]
    assert first_sampler.started == [record["request_id"] for record in first_requests]
    assert first_sampler.stopped == 4


def test_every_generation_has_a_unique_leading_cache_buster(tmp_path: Path) -> None:
    client = FakeClient()

    run_experiment(
        make_config(tmp_path),
        client_factory=lambda _url: client,
        sampler_factory=lambda **_kwargs: FakeSampler(),
    )

    prefixes = [request.prompt.splitlines()[0] for request in client.requests]
    expected = [
        hashlib.sha256(request.request_id.encode("utf-8")).hexdigest()
        for request in client.requests
    ]
    assert prefixes == expected
    assert len(prefixes) == len(set(prefixes))
    assert all("kv_cache" not in request.options for request in client.requests)
    assert all(request.options["num_ctx"] == 4096 for request in client.requests)
    assert all(request.options["num_gpu"] == 999 for request in client.requests)
    assert client.preload_options == [
        {"num_ctx": 4096, "num_gpu": 999},
        {"num_ctx": 4096, "num_gpu": 999},
    ]


def test_run_requires_two_warmups_to_establish_a_cache_baseline(tmp_path: Path) -> None:
    config = make_config(tmp_path, warmups=1)

    with pytest.raises(RunnerPreflightError, match="two warm-up"):
        run_experiment(
            config,
            client_factory=lambda _url: FakeClient(),
            sampler_factory=lambda **_kwargs: FakeSampler(),
        )

    assert not config.output_dir.exists()


def test_final_warmup_cache_count_is_applied_to_measured_requests(tmp_path: Path) -> None:
    client = FakeClient(cached_counts=(20, 21, 21, 20, 21, 20))

    run_dir = run_experiment(
        make_config(tmp_path),
        client_factory=lambda _url: client,
        sampler_factory=lambda **_kwargs: FakeSampler(),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    assert manifest["models"][0]["template_cache_baseline_tokens"] == 21
    assert all(record["valid"] is True for record in outputs)
    assert {record["metrics"]["template_cache_baseline_tokens"] for record in outputs} == {21}
    assert {record["metrics"]["excess_cached_prompt_tokens"] for record in outputs} == {0}


def test_missing_final_warmup_cache_count_aborts_before_measurement(tmp_path: Path) -> None:
    client = FakeClient(cached_counts=(0, None))
    config = make_config(tmp_path)

    with pytest.raises(RunnerError, match="prompt_eval_cached_count"):
        run_experiment(
            config,
            client_factory=lambda _url: client,
            sampler_factory=lambda **_kwargs: FakeSampler(),
        )

    assert len(client.requests) == 2
    run_dir = next(config.output_dir.iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["started_requests"] == 0


@pytest.mark.parametrize("placement", [False, None])
def test_preflight_requires_confirmed_full_gpu_placement(
    tmp_path: Path, placement: bool | None
) -> None:
    client = FakeClient(fully_on_gpu=placement)
    sampler = FakeSampler()

    with pytest.raises(RunnerPreflightError, match="fully on GPU"):
        run_experiment(
            make_config(tmp_path),
            client_factory=lambda _url: client,
            sampler_factory=lambda **_kwargs: sampler,
        )

    assert not (tmp_path / "runs").exists()
    assert client.closed is True
    assert sampler.closed is True


def test_interrupt_stops_telemetry_and_preserves_partial_run(tmp_path: Path) -> None:
    config = make_config(tmp_path, repetitions=1)
    client = FakeClient(interrupt_at=3)
    sampler = FakeSampler()

    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            config,
            client_factory=lambda _url: client,
            sampler_factory=lambda **_kwargs: sampler,
        )

    run_dirs = tuple(config.output_dir.iterdir())
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert manifest["completed_requests"] == 0
    assert len(read_jsonl(run_dirs[0] / "requests.jsonl")) == 1
    assert read_jsonl(run_dirs[0] / "outputs.jsonl") == ()
    assert len(read_gzip_jsonl(run_dirs[0] / "telemetry.jsonl.gz")) == 2
    assert sampler.stopped == 1
    assert sampler.closed is True


def test_completed_run_writes_auditable_manifest_and_validation(tmp_path: Path) -> None:
    config = make_config(tmp_path, repetitions=1, tariff=5.0)

    run_dir = run_experiment(
        config,
        client_factory=lambda _url: FakeClient(),
        sampler_factory=lambda **_kwargs: FakeSampler(),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    assert manifest["schema_version"] == 1
    assert manifest["status"] == "completed"
    assert manifest["runtime"]["name"] == "ollama"
    assert manifest["runtime"]["version"] == "0.99.0-test"
    assert manifest["models"][0]["digest"] == DIGEST
    assert manifest["models"][0]["fully_on_gpu"] is True
    assert manifest["models"][0]["template_cache_baseline_tokens"] == 0
    assert manifest["config_sha256"]
    assert manifest["prompt_set_sha256"]
    assert set(manifest["artifact_sha256"]) == {
        "config.resolved.toml",
        "requests.jsonl",
        "outputs.jsonl",
        "telemetry.jsonl.gz",
    }
    assert validation["ok"] is True
    assert all(record["valid"] is True for record in outputs)
    assert all(record["metrics"]["gpu_energy_joules"] == 1.2 for record in outputs)
