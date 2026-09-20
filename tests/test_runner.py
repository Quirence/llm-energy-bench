"""Tests for the experiment runner and the derived request metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fake_runtime import DIGEST, FakeOllamaClient, FakeSampler, capabilities, sample
from llm_energy_bench.config import ExperimentConfig, InferenceOptions, load_config, load_prompts
from llm_energy_bench.nvml import EnergySource
from llm_energy_bench.ollama import InvalidKind
from llm_energy_bench.results import (
    MANIFEST,
    OUTPUTS,
    REQUESTS,
    TELEMETRY,
    RunStatus,
    read_gzip_jsonl,
    read_jsonl,
    validate_run,
)
from llm_energy_bench.runner import (
    PreflightFailed,
    compute_request_metrics,
    integrate_power,
    run_experiment,
)

PROMPTS = [
    {"id": "short-01", "category": "short", "prompt": "one"},
    {"id": "long-01", "category": "long", "prompt": "two"},
    {"id": "scored-01", "category": "scored", "prompt": "three", "expect_contains": ["3"]},
]


def build_config(tmp_path: Path, **overrides: object) -> ExperimentConfig:
    tmp_path.mkdir(parents=True, exist_ok=True)
    prompt_path = tmp_path / "prompts.jsonl"
    prompt_path.write_text(
        "\n".join(json.dumps(record) for record in PROMPTS) + "\n", encoding="utf-8"
    )
    defaults: dict[str, object] = {
        "experiment_id": "test",
        "host_id": "host-a",
        "output_dir": tmp_path / "runs",
        "ollama_url": "http://127.0.0.1:11434",
        "models": ("llama3.2:3b-instruct-q4_K_M",),
        "prompt_path": prompt_path,
        "gpu_index": 0,
        "telemetry_interval_ms": 100,
        "warmup_requests": 2,
        "repetitions": 2,
        "order_seed": 42,
        "concurrency": 1,
        "options": InferenceOptions(),
        "tariff_per_kwh": None,
        "currency": None,
        "source_path": tmp_path / "experiment.toml",
    }
    return ExperimentConfig(**(defaults | overrides))  # type: ignore[arg-type]


def run(
    tmp_path: Path, client: FakeOllamaClient, sampler: FakeSampler, **overrides: object
) -> Path:
    return run_experiment(build_config(tmp_path, **overrides), client=client, sampler=sampler)


# --------------------------------------------------------------------------
# Ordering, warm-ups, and cache busting
# --------------------------------------------------------------------------


def test_a_run_writes_one_record_per_prompt_repetition_and_model(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())

    assert len(read_jsonl(run_dir / REQUESTS)) == 3 * 2
    assert len(read_jsonl(run_dir / OUTPUTS)) == 3 * 2


def test_warmup_requests_are_executed_but_excluded_from_the_records(tmp_path: Path) -> None:
    client = FakeOllamaClient()
    run_dir = run(tmp_path, client, FakeSampler())

    assert len(client.requests_seen) == 2 + 6, "two warm-ups precede six measured requests"
    recorded = {r["request_id"] for r in read_jsonl(run_dir / REQUESTS)}
    assert not any("warmup" in request_id for request_id in recorded)


def test_warmups_run_before_any_measured_request(tmp_path: Path) -> None:
    client = FakeOllamaClient()
    run(tmp_path, client, FakeSampler())

    first_two = [r.request_id for r in client.requests_seen[:2]]
    assert all("warmup" in request_id for request_id in first_two)


def test_the_measured_order_is_deterministic_for_a_given_seed(tmp_path: Path) -> None:
    first = run(tmp_path / "a", FakeOllamaClient(), FakeSampler())
    second = run(tmp_path / "b", FakeOllamaClient(), FakeSampler())

    def order(run_dir: Path) -> list[str]:
        return [r["prompt_id"] for r in read_jsonl(run_dir / REQUESTS)]

    assert order(first) == order(second)


def test_a_different_seed_produces_a_different_order(tmp_path: Path) -> None:
    first = run(tmp_path / "a", FakeOllamaClient(), FakeSampler(), order_seed=1)
    second = run(tmp_path / "b", FakeOllamaClient(), FakeSampler(), order_seed=999)

    def order(run_dir: Path) -> list[str]:
        return [(r["prompt_id"], r["repetition"]) for r in read_jsonl(run_dir / REQUESTS)]

    assert order(first) != order(second)


def test_the_order_is_shuffled_rather_than_grouped_by_prompt(tmp_path: Path) -> None:
    """Grouped repetitions would confound thermal drift with prompt identity."""
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler(), repetitions=4)
    ids = [r["prompt_id"] for r in read_jsonl(run_dir / REQUESTS)]

    grouped = sorted(ids)
    assert ids != grouped


def test_every_measured_prompt_gets_a_unique_leading_cache_buster(tmp_path: Path) -> None:
    """A shared prefix would let the KV cache skip prefill and fake the numbers."""
    client = FakeOllamaClient()
    run(tmp_path, client, FakeSampler())

    measured = client.prompts_seen[2:]
    leaders = [text.split("\n", 1)[0] for text in measured]
    assert len(set(leaders)) == len(measured)
    for text, leader in zip(measured, leaders, strict=True):
        assert text.endswith(("one", "two", "three")), "the prompt body survives intact"
        assert leader != ""


def test_the_cache_buster_is_recorded_so_the_sent_prompt_is_reproducible(
    tmp_path: Path,
) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())

    records = read_jsonl(run_dir / REQUESTS)
    assert all(record["cache_buster"] for record in records)
    assert len({record["cache_buster"] for record in records}) == len(records)


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------


def test_a_missing_model_stops_the_run_before_any_inference(tmp_path: Path) -> None:
    client = FakeOllamaClient(installed=())

    with pytest.raises(PreflightFailed, match="not installed"):
        run(tmp_path, client, FakeSampler())

    assert client.requests_seen == []


def test_partial_cpu_offload_invalidates_a_primary_gpu_run(tmp_path: Path) -> None:
    client = FakeOllamaClient(size_bytes=2_000_000_000, size_vram_bytes=1_200_000_000)

    with pytest.raises(PreflightFailed, match="60"):
        run(tmp_path, client, FakeSampler())

    assert client.requests_seen == []


def test_a_fully_resident_model_passes_preflight(tmp_path: Path) -> None:
    client = FakeOllamaClient(size_bytes=2_000_000_000, size_vram_bytes=2_000_000_000)

    assert run(tmp_path, client, FakeSampler())


def test_an_unknown_placement_stops_the_run(tmp_path: Path) -> None:
    """Unknown placement is not assumed to be full GPU residency."""
    client = FakeOllamaClient(size_bytes=2_000_000_000)
    client.size_vram_bytes = None

    with pytest.raises(PreflightFailed, match="placement"):
        run(tmp_path, client, FakeSampler())


def test_a_gpu_without_any_energy_source_stops_the_run(tmp_path: Path) -> None:
    sampler = FakeSampler(caps=capabilities(EnergySource.UNAVAILABLE))

    with pytest.raises(PreflightFailed, match="energy"):
        run(tmp_path, FakeOllamaClient(), sampler)


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------


def test_a_completed_run_produces_a_valid_run_directory(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())
    report = validate_run(run_dir)

    assert report.ok is True, report.errors
    assert report.status is RunStatus.COMPLETED


def test_the_manifest_records_the_controls_and_the_environment(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())
    manifest = json.loads((run_dir / MANIFEST).read_text(encoding="utf-8"))

    assert manifest["status"] == "completed"
    assert manifest["config"]["options"]["num_ctx"] == 4096
    assert manifest["config_fingerprint"]
    assert manifest["prompt_set_fingerprint"]
    assert manifest["gpu"]["gpu_fingerprint"] == "54a50433af3c357a"
    assert manifest["gpu"]["energy_source"] == "total_energy_counter"
    assert manifest["runtime"]["ollama_version"] == "0.3.14"
    assert manifest["models"][0]["digest"] == DIGEST


def test_the_manifest_carries_no_private_data(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())
    text = (run_dir / MANIFEST).read_text(encoding="utf-8")

    assert "/home/" not in text
    assert str(tmp_path) not in text


def test_outputs_are_stored_separately_from_metrics(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())

    outputs = read_jsonl(run_dir / OUTPUTS)
    assert outputs[0]["text"] == "generated text"
    assert "text" not in read_jsonl(run_dir / REQUESTS)[0]


def test_telemetry_is_written_for_every_measured_request(tmp_path: Path) -> None:
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler(samples_per_request=4))

    samples = read_gzip_jsonl(run_dir / TELEMETRY)
    assert len(samples) == 6 * 4
    assert {s["request_id"] for s in samples} == {
        r["request_id"] for r in read_jsonl(run_dir / REQUESTS)
    }


def test_records_reach_disk_as_the_run_proceeds(tmp_path: Path) -> None:
    """An interrupted campaign keeps everything measured up to the interrupt."""
    client = FakeOllamaClient()
    config = build_config(tmp_path)
    counts: list[int] = []

    def spy(request):  # type: ignore[no-untyped-def]
        runs = list(config.output_dir.iterdir()) if config.output_dir.is_dir() else []
        if runs:
            counts.append(len(read_jsonl(runs[0] / REQUESTS)))
        return FakeOllamaClient.generate_stream(client, request)

    client.generate_stream = spy  # type: ignore[method-assign]
    run_dir = run_experiment(config, client=client, sampler=FakeSampler())

    measured = counts[2:]  # the warm-ups precede the run directory's first record
    assert measured == sorted(measured), "records only ever accumulate"
    assert measured[-1] > measured[0], "each request is written before the next one starts"
    assert len(read_jsonl(run_dir / REQUESTS)) == 6


# --------------------------------------------------------------------------
# Failure and interruption
# --------------------------------------------------------------------------


def test_an_invalid_generation_is_recorded_without_aborting_the_run(tmp_path: Path) -> None:
    client = FakeOllamaClient(fail_on={"req-0002": InvalidKind.NO_OUTPUT})
    run_dir = run(tmp_path, client, FakeSampler())

    records = read_jsonl(run_dir / REQUESTS)
    assert len(records) == 6, "the run continues past an invalid request"

    failed = [record for record in records if record["request_id"] == "req-0002"][0]
    assert failed["valid"] is False
    assert failed["invalid_kind"] == "no_output"
    assert failed["energy_joules"] is not None, "telemetry is kept even for an invalid request"
    assert failed["joules_per_output_token"] is None
    assert all(r["valid"] for r in records if r["request_id"] != "req-0002")


def test_an_invalid_request_never_divides_by_zero(tmp_path: Path) -> None:
    client = FakeOllamaClient(eval_count=0)
    run_dir = run(tmp_path, client, FakeSampler())

    for record in read_jsonl(run_dir / REQUESTS):
        assert record["joules_per_output_token"] is None
        assert record["output_tokens_per_joule"] is None
        assert record["valid"] is False


def test_an_interrupted_run_is_preserved_with_its_status(tmp_path: Path) -> None:
    client = FakeOllamaClient()
    config = build_config(tmp_path)
    sampler = FakeSampler()

    def interrupt_on_third(request):  # type: ignore[no-untyped-def]
        if len(client.requests_seen) >= 5:
            raise KeyboardInterrupt
        return FakeOllamaClient.generate_stream(client, request)

    client.generate_stream = interrupt_on_third  # type: ignore[method-assign]
    run_dir = run_experiment(config, client=client, sampler=sampler)

    manifest = json.loads((run_dir / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert 0 < len(read_jsonl(run_dir / REQUESTS)) < 6
    assert validate_run(run_dir).status is RunStatus.INTERRUPTED


def test_telemetry_is_stopped_even_when_generation_raises(tmp_path: Path) -> None:
    client = FakeOllamaClient()
    sampler = FakeSampler()
    client.raise_on_request = {}

    def explode(request):  # type: ignore[no-untyped-def]
        if len(client.requests_seen) >= 3:
            raise RuntimeError("transport exploded")
        return FakeOllamaClient.generate_stream(client, request)

    client.generate_stream = explode  # type: ignore[method-assign]
    run_dir = run_experiment(build_config(tmp_path), client=client, sampler=sampler)

    assert sampler.is_sampling is False
    assert len(sampler.started) == len(sampler.stopped), "every start was matched by a stop"
    assert sampler.closed >= 1
    assert json.loads((run_dir / MANIFEST).read_text())["status"] == "failed"


def test_the_sampler_and_client_are_closed_on_the_happy_path(tmp_path: Path) -> None:
    client = FakeOllamaClient()
    sampler = FakeSampler()
    run(tmp_path, client, sampler)

    assert sampler.closed >= 1
    assert sampler.is_sampling is False


# --------------------------------------------------------------------------
# Energy accounting
# --------------------------------------------------------------------------


def test_the_total_energy_counter_is_preferred_when_supported(tmp_path: Path) -> None:
    sampler = FakeSampler(samples_per_request=3, energy_step_j=4.5)
    run_dir = run(tmp_path, FakeOllamaClient(), sampler)

    record = read_jsonl(run_dir / REQUESTS)[0]
    assert record["energy_source"] == "total_energy_counter"
    # Three samples advance the counter three times; the window spans two steps.
    assert record["energy_joules"] == pytest.approx(9.0)


def test_power_integration_is_used_when_no_counter_exists(tmp_path: Path) -> None:
    sampler = FakeSampler(caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION), power=50.0)
    run_dir = run(tmp_path, FakeOllamaClient(), sampler)

    record = read_jsonl(run_dir / REQUESTS)[0]
    assert record["energy_source"] == "power_instant_integration"
    # Constant 50 W across a two-second window.
    assert record["energy_joules"] == pytest.approx(100.0)


def test_a_backwards_energy_counter_yields_null_energy_not_a_negative_number(
    tmp_path: Path,
) -> None:
    """A driver reset inside a request must not be reported as negative energy."""
    samples = (
        sample("r", 0.0, energy_j=1000.0),
        sample("r", 1.0, energy_j=5.0),
    )
    metrics = compute_request_metrics(
        result=_stub_result(),
        samples=samples,
        caps=capabilities(EnergySource.TOTAL_ENERGY_COUNTER),
        tariff_per_kwh=None,
        currency=None,
    )

    assert metrics.energy_joules is None
    assert "backwards" in (metrics.energy_note or "")


def test_energy_is_null_when_a_request_has_no_telemetry(tmp_path: Path) -> None:
    metrics = compute_request_metrics(
        result=_stub_result(),
        samples=(),
        caps=capabilities(),
        tariff_per_kwh=None,
        currency=None,
    )

    assert metrics.energy_joules is None
    assert metrics.average_power_watts is None
    assert metrics.joules_per_output_token is None


def test_a_single_sample_cannot_produce_an_energy_figure() -> None:
    metrics = compute_request_metrics(
        result=_stub_result(),
        samples=(sample("r", 0.0, energy_j=1000.0),),
        caps=capabilities(),
        tariff_per_kwh=None,
        currency=None,
    )

    assert metrics.energy_joules is None


# --------------------------------------------------------------------------
# Integration helper
# --------------------------------------------------------------------------


def test_trapezoidal_integration_of_constant_power() -> None:
    samples = [(0.0, 40.0), (1.0, 40.0), (2.0, 40.0)]

    assert integrate_power(samples) == pytest.approx(80.0)


def test_trapezoidal_integration_of_a_ramp() -> None:
    """A linear ramp from 0 W to 100 W over 2 s carries 100 J."""
    samples = [(0.0, 0.0), (1.0, 50.0), (2.0, 100.0)]

    assert integrate_power(samples) == pytest.approx(100.0)


def test_integration_needs_at_least_two_points() -> None:
    assert integrate_power([(0.0, 40.0)]) is None
    assert integrate_power([]) is None


def test_integration_ignores_a_zero_length_window() -> None:
    assert integrate_power([(1.0, 40.0), (1.0, 40.0)]) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Derived metric formulas
# --------------------------------------------------------------------------


def _stub_result(eval_count: int | None = 100, latency_s: float = 2.0):  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from llm_energy_bench.ollama import InferenceResult

    now = datetime.now(UTC)
    return InferenceResult(
        request_id="r",
        model="m",
        model_digest=DIGEST,
        started_utc=now,
        ended_utc=now,
        t_start_s=0.0,
        t_first_chunk_s=0.2,
        t_first_token_s=0.2,
        t_end_s=latency_s,
        ttft_s=0.2,
        latency_s=latency_s,
        text="text",
        chunk_count=10,
        done=True,
        done_reason="stop",
        http_status=200,
        prompt_eval_count=300,
        eval_count=eval_count,
        total_duration_ns=2_000_000_000,
        load_duration_ns=0,
        prompt_eval_duration_ns=400_000_000,
        eval_duration_ns=1_500_000_000,
        valid=True,
        invalid_kind=None,
        invalid_reason=None,
    )


def metrics_for(energy_j: float, eval_count: int | None = 100, **kwargs):  # type: ignore[no-untyped-def]
    """Build metrics over a window whose integrated energy is ``energy_j``."""
    watts = energy_j / 2.0  # a two-second window at constant power
    samples = (sample("r", 0.0, power=watts), sample("r", 2.0, power=watts))
    return compute_request_metrics(
        result=_stub_result(eval_count=eval_count),
        samples=samples,
        caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        **{"tariff_per_kwh": None, "currency": None} | kwargs,
    )


def test_joules_per_output_token() -> None:
    metrics = metrics_for(energy_j=200.0, eval_count=100)

    assert metrics.energy_joules == pytest.approx(200.0)
    assert metrics.joules_per_output_token == pytest.approx(2.0)


def test_output_tokens_per_joule_is_the_reciprocal() -> None:
    metrics = metrics_for(energy_j=200.0, eval_count=100)

    assert metrics.output_tokens_per_joule == pytest.approx(0.5)


def test_throughput_splits_prefill_decode_and_end_to_end() -> None:
    metrics = metrics_for(energy_j=200.0, eval_count=100)

    assert metrics.decode_tokens_per_s == pytest.approx(100 / 1.5)
    assert metrics.prefill_tokens_per_s == pytest.approx(300 / 0.4)
    assert metrics.end_to_end_tokens_per_s == pytest.approx(50.0)


def test_cost_is_null_without_a_tariff() -> None:
    metrics = metrics_for(energy_j=200.0)

    assert metrics.cost_per_million_output_tokens is None
    assert metrics.currency is None


def test_cost_per_million_output_tokens_uses_the_tariff() -> None:
    """2 J/token -> 2e6 J per million tokens -> 0.5556 kWh -> 5.556 at 10 per kWh."""
    metrics = metrics_for(energy_j=200.0, eval_count=100, tariff_per_kwh=10.0, currency="RUB")

    assert metrics.cost_per_million_output_tokens == pytest.approx(5.5555, rel=1e-3)
    assert metrics.currency == "RUB"


def test_power_and_thermal_fields_are_summarised() -> None:
    samples = (
        sample("r", 0.0, power=40.0, temperature=55, vram_used=1_000),
        sample("r", 1.0, power=60.0, temperature=70, vram_used=3_000),
    )
    metrics = compute_request_metrics(
        result=_stub_result(),
        samples=samples,
        caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION),
        tariff_per_kwh=None,
        currency=None,
    )

    assert metrics.average_power_watts == pytest.approx(50.0)
    assert metrics.max_power_watts == pytest.approx(60.0)
    assert metrics.start_temperature_c == 55
    assert metrics.max_temperature_c == 70
    assert metrics.start_vram_used_bytes == 1_000
    assert metrics.peak_vram_used_bytes == 3_000
    assert metrics.power_limit_watts == pytest.approx(60.0)


def test_metrics_serialize_with_nulls_for_unavailable_fields() -> None:
    metrics = compute_request_metrics(
        result=_stub_result(eval_count=None),
        samples=(),
        caps=capabilities(),
        tariff_per_kwh=None,
        currency=None,
    )
    payload = json.loads(json.dumps(metrics.to_dict()))

    assert payload["energy_joules"] is None
    assert payload["joules_per_output_token"] is None
    assert payload["valid"] is False


# --------------------------------------------------------------------------
# The shipped pilot config
# --------------------------------------------------------------------------


def test_the_shipped_pilot_config_runs_end_to_end(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(repo_root / "configs" / "pilot.toml")
    config = ExperimentConfig(
        **{**{f: getattr(config, f) for f in config.__slots__}, "output_dir": tmp_path / "runs"}
    )
    prompts = load_prompts(config.prompt_path)

    run_dir = run_experiment(config, client=FakeOllamaClient(), sampler=FakeSampler())

    assert len(read_jsonl(run_dir / REQUESTS)) == len(prompts) * config.repetitions == 18
    assert validate_run(run_dir).ok is True


# --------------------------------------------------------------------------
# Quality scoring
# --------------------------------------------------------------------------


def test_a_scored_prompt_is_judged_at_measurement_time(tmp_path: Path) -> None:
    """The run directory must stay self-contained: no reaching back to the prompt file."""
    run_dir = run(tmp_path, FakeOllamaClient(), FakeSampler())
    records = {r["prompt_id"]: r for r in read_jsonl(run_dir / REQUESTS)}

    assert records["scored-01"]["quality_pass"] is False, "'generated text' lacks '3'"
    assert records["short-01"]["quality_pass"] is None, "unscored prompts are not judged"


def test_scoring_is_case_insensitive_and_requires_every_fragment() -> None:
    from llm_energy_bench.config import PromptCase, PromptCategory
    from llm_energy_bench.runner import score_output

    prompt = PromptCase(
        prompt_id="s",
        category=PromptCategory.SCORED,
        prompt="q",
        expect_contains=("Paris", "France"),
    )

    assert score_output(prompt, "the capital is paris, in FRANCE") is True
    assert score_output(prompt, "the capital is Paris") is False
    assert score_output(prompt, "") is False


def test_an_unscored_prompt_is_never_judged() -> None:
    from llm_energy_bench.config import PromptCase, PromptCategory
    from llm_energy_bench.runner import score_output

    prompt = PromptCase(prompt_id="s", category=PromptCategory.SHORT, prompt="q")

    assert score_output(prompt, "anything at all") is None
