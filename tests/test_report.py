"""Tests for environment diagnosis and reproducible aggregate reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from llm_energy_bench.cli import doctor_environment
from llm_energy_bench.config import ExperimentConfig, InferenceOptions
from llm_energy_bench.nvml import EnergySource, GpuCapabilities
from llm_energy_bench.ollama import ModelNotFound, OllamaUnavailable, RunningModel
from llm_energy_bench.results import (
    GzipJsonlWriter,
    JsonlWriter,
    build_report,
    write_json,
    write_text,
)

MODEL = "llama3.2:3b-instruct-q4_K_M"
DIGEST = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"


def config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="pilot",
        host_id="test-host",
        output_dir=tmp_path / "runs",
        ollama_url="http://ollama.test:11434",
        models=(MODEL,),
        prompt_path=tmp_path / "prompts.jsonl",
        gpu_index=0,
        telemetry_interval_ms=100,
        warmup_requests=2,
        repetitions=3,
        order_seed=42,
        concurrency=1,
        options=InferenceOptions(),
        tariff_per_kwh=None,
        currency=None,
        source_path=tmp_path / "pilot.toml",
    )


def gpu(source: EnergySource = EnergySource.POWER_INSTANT_INTEGRATION) -> GpuCapabilities:
    return GpuCapabilities(
        gpu_index=0,
        name="Fake RTX",
        gpu_fingerprint="0123456789abcdef",
        driver_version="999.1",
        vram_total_bytes=8_000_000_000,
        supports_total_energy=source is EnergySource.TOTAL_ENERGY_COUNTER,
        supports_power_instant=source is EnergySource.POWER_INSTANT_INTEGRATION,
        supports_power_legacy=True,
        supports_temperature=True,
        supports_utilization=True,
        supports_clocks=True,
        supports_power_limit=True,
        power_limit_watts=80.0,
        energy_source=source,
        energy_fallback_reason=(
            "total-energy counter unsupported"
            if source is not EnergySource.TOTAL_ENERGY_COUNTER
            else None
        ),
    )


class DoctorClient:
    def __init__(self, *, missing: bool = False, placement: bool | None = True) -> None:
        self.missing = missing
        self.placement = placement

    def __enter__(self) -> DoctorClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def version(self) -> str:
        return "0.99.0-test"

    def preload(self, model: str) -> RunningModel:
        if self.missing:
            raise ModelNotFound(f"model {model!r} is not installed")
        size = 3_000_000_000
        size_vram = None if self.placement is None else size if self.placement else size - 1
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


class UnavailableDoctorClient(DoctorClient):
    def version(self) -> str:
        raise OllamaUnavailable("connection refused")


class DoctorSampler:
    def __init__(self, capabilities: GpuCapabilities) -> None:
        self.capabilities = capabilities

    def __enter__(self) -> DoctorSampler:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def probe(self, _index: int | None = None) -> GpuCapabilities:
        return self.capabilities


def diagnose(
    tmp_path: Path,
    *,
    client: DoctorClient | None = None,
    capabilities: GpuCapabilities | None = None,
) -> dict[str, Any]:
    actual_client = client or DoctorClient()
    actual_gpu = capabilities or gpu()
    return doctor_environment(
        config(tmp_path),
        client_factory=lambda _url: actual_client,
        sampler_factory=lambda **_kwargs: DoctorSampler(actual_gpu),
    )


def test_doctor_reports_unavailable_ollama_without_a_traceback(tmp_path: Path) -> None:
    report = diagnose(tmp_path, client=UnavailableDoctorClient())

    assert report["ok"] is False
    assert report["runtime"]["available"] is False
    assert "connection refused" in report["runtime"]["error"]


def test_doctor_reports_a_missing_model(tmp_path: Path) -> None:
    report = diagnose(tmp_path, client=DoctorClient(missing=True))

    assert report["ok"] is False
    assert report["models"][0]["installed"] is False
    assert "not installed" in report["models"][0]["error"]


def test_doctor_accepts_power_integration_when_energy_counter_is_unsupported(
    tmp_path: Path,
) -> None:
    report = diagnose(tmp_path, capabilities=gpu(EnergySource.POWER_INSTANT_INTEGRATION))

    assert report["ok"] is True
    assert report["gpu"]["supports_total_energy"] is False
    assert report["gpu"]["energy_source"] == "power_instant_integration"
    assert report["gpu"]["energy_fallback_reason"]


def test_doctor_rejects_partial_gpu_placement(tmp_path: Path) -> None:
    report = diagnose(tmp_path, client=DoctorClient(placement=False))

    assert report["ok"] is False
    assert report["models"][0]["fully_on_gpu"] is False


def test_doctor_json_is_sanitized(tmp_path: Path) -> None:
    payload = json.dumps(diagnose(tmp_path), ensure_ascii=False)

    assert "Quirence" not in payload
    assert "C:\\Users" not in payload
    assert "GPU-" not in payload
    assert "0123456789abcdef" in payload


def output_record(
    request_id: str,
    *,
    prompt_id: str,
    category: str,
    latency: float,
    output_tokens: int,
    energy: float,
    quality: float | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "model": MODEL,
        "model_digest": DIGEST,
        "prompt_id": prompt_id,
        "prompt_category": category,
        "repetition": 0,
        "valid": True,
        "metrics": {
            "latency_seconds": latency,
            "ttft_seconds": latency / 4,
            "output_tokens": output_tokens,
            "decode_tokens_per_second": output_tokens / latency,
            "end_to_end_tokens_per_second": output_tokens / latency,
            "average_gpu_power_watts": energy / latency,
            "observed_peak_gpu_power_watts": energy / latency + 1,
            "gpu_energy_joules": energy,
            "joules_per_output_token": energy / output_tokens,
            "output_tokens_per_joule": output_tokens / energy,
            "quality_score": quality,
        },
    }


def make_run(
    root: Path,
    run_id: str,
    records: list[dict[str, Any]],
    *,
    host_id: str = "host-a",
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "status": "completed",
            "host_id": host_id,
            "models": [{"name": MODEL, "digest": DIGEST}],
            "controls": {"tariff_per_kwh": None, "currency": None},
        },
    )
    write_text(run_dir / "config.resolved.toml", '[experiment]\nid = "report-test"\n')
    with JsonlWriter(run_dir / "requests.jsonl") as writer:
        for record in records:
            writer.write({"request_id": record["request_id"]})
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        for record in records:
            writer.write(record)
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        for record in records:
            writer.write({"request_id": record["request_id"], "monotonic_s": 0.0})
    return run_dir


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_report_uses_median_and_interpolated_iqr(tmp_path: Path) -> None:
    records = [
        output_record(
            f"r{index}",
            prompt_id=f"p{index}",
            category="short",
            latency=latency,
            output_tokens=10,
            energy=10,
        )
        for index, latency in enumerate((1.0, 2.0, 3.0, 4.0), start=1)
    ]
    report = build_report((make_run(tmp_path, "run-a", records),))
    row = rows(report.summary_csv)[0]

    assert float(row["latency_median_seconds"]) == 2.5
    assert float(row["latency_iqr_seconds"]) == 1.5


def test_report_uses_ratios_of_sums_not_means_of_request_ratios(tmp_path: Path) -> None:
    records = [
        output_record(
            "r1",
            prompt_id="p1",
            category="short",
            latency=1.0,
            output_tokens=10,
            energy=1.0,
        ),
        output_record(
            "r2",
            prompt_id="p2",
            category="short",
            latency=9.0,
            output_tokens=20,
            energy=9.0,
        ),
    ]
    report = build_report((make_run(tmp_path, "run-a", records),))
    row = rows(report.summary_csv)[0]

    assert float(row["end_to_end_tokens_per_second"]) == 3.0
    assert float(row["output_tokens_per_joule"]) == 3.0


def test_quality_gives_each_prompt_equal_weight_after_repetitions(tmp_path: Path) -> None:
    records = [
        output_record(
            "a1",
            prompt_id="prompt-a",
            category="scored",
            latency=1,
            output_tokens=1,
            energy=1,
            quality=1.0,
        ),
        output_record(
            "a2",
            prompt_id="prompt-a",
            category="scored",
            latency=1,
            output_tokens=1,
            energy=1,
            quality=1.0,
        ),
        output_record(
            "b1",
            prompt_id="prompt-b",
            category="scored",
            latency=1,
            output_tokens=1,
            energy=1,
            quality=0.0,
        ),
    ]
    report = build_report((make_run(tmp_path, "run-a", records),))
    row = rows(report.summary_csv)[0]

    assert float(row["quality_score"]) == 0.5
    assert row["ranking_eligible"] == "false"


def test_quality_floor_is_inclusive_at_75_percent(tmp_path: Path) -> None:
    records = [
        output_record(
            f"r{index}",
            prompt_id=f"p{index}",
            category="scored",
            latency=1,
            output_tokens=1,
            energy=1,
            quality=score,
        )
        for index, score in enumerate((1.0, 1.0, 1.0, 0.0), start=1)
    ]
    report = build_report((make_run(tmp_path, "run-a", records),))
    row = rows(report.summary_csv)[0]

    assert float(row["quality_score"]) == 0.75
    assert row["ranking_eligible"] == "true"


def test_cross_run_speed_and_energy_rankings_can_invert(tmp_path: Path) -> None:
    quality = output_record(
        "quality",
        prompt_id="quality",
        category="scored",
        latency=1,
        output_tokens=1,
        energy=1,
        quality=1.0,
    )
    fast = make_run(
        tmp_path,
        "run-fast",
        [
            output_record(
                "fast",
                prompt_id="short",
                category="short",
                latency=1,
                output_tokens=10,
                energy=100,
            ),
            quality,
        ],
        host_id="fast-host",
    )
    efficient = make_run(
        tmp_path,
        "run-efficient",
        [
            output_record(
                "efficient",
                prompt_id="short",
                category="short",
                latency=2,
                output_tokens=10,
                energy=10,
            ),
            {**quality, "request_id": "quality-efficient"},
        ],
        host_id="efficient-host",
    )

    report = build_report((fast, efficient))
    short_rows = {
        row["run_id"]: row
        for row in rows(report.summary_csv)
        if row["prompt_category"] == "short"
    }

    assert short_rows["run-fast"]["speed_rank"] == "1"
    assert short_rows["run-fast"]["energy_rank"] == "2"
    assert short_rows["run-efficient"]["speed_rank"] == "2"
    assert short_rows["run-efficient"]["energy_rank"] == "1"
    assert "speed and energy rankings differ" in report.report_markdown.read_text(
        encoding="utf-8"
    ).lower()
