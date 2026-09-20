"""Tests for the environment doctor and the derived reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from fake_runtime import FakeOllamaClient, FakeSampler, capabilities
from llm_energy_bench import cli
from llm_energy_bench.nvml import EnergySource, NvmlUnavailable
from llm_energy_bench.ollama import OllamaUnavailable
from llm_energy_bench.results import (
    REPORT,
    SUMMARY,
    build_report,
    diagnose,
)
from llm_energy_bench.runner import run_experiment
from test_runner import build_config

# --------------------------------------------------------------------------
# Doctor
# --------------------------------------------------------------------------


def test_a_healthy_host_reports_ok() -> None:
    report = diagnose(client=FakeOllamaClient(), sampler=FakeSampler())

    assert report.ok is True
    assert report.problems == ()
    assert report.ollama_version == "0.3.14"
    assert report.gpu["energy_source"] == "total_energy_counter"


def test_an_unavailable_ollama_is_reported_not_raised() -> None:
    class Dead(FakeOllamaClient):
        def version(self) -> str:
            raise OllamaUnavailable("connection refused")

    report = diagnose(client=Dead(), sampler=FakeSampler())

    assert report.ok is False
    assert any("ollama" in problem.lower() for problem in report.problems)


def test_an_unavailable_gpu_is_reported_not_raised() -> None:
    class NoGpu(FakeSampler):
        def open(self) -> None:
            raise NvmlUnavailable("NVML Shared Library Not Found")

    report = diagnose(client=FakeOllamaClient(), sampler=NoGpu())

    assert report.ok is False
    assert any("nvml" in problem.lower() or "gpu" in problem.lower() for problem in report.problems)


def test_a_missing_model_is_named(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    report = diagnose(client=FakeOllamaClient(installed=()), sampler=FakeSampler(), config=config)

    assert report.ok is False
    assert any("llama3.2:3b-instruct-q4_K_M" in problem for problem in report.problems)


def test_an_installed_model_passes(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    report = diagnose(client=FakeOllamaClient(), sampler=FakeSampler(), config=config)

    assert report.ok is True


def test_an_unsupported_energy_counter_is_reported_as_a_fallback_not_a_failure() -> None:
    sampler = FakeSampler(caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION))
    report = diagnose(client=FakeOllamaClient(), sampler=sampler)

    assert report.ok is True, "integrating power is a documented fallback"
    assert any("counter" in note.lower() for note in report.notes)
    assert report.gpu["energy_source"] == "power_instant_integration"


def test_a_gpu_with_no_energy_source_at_all_is_a_problem() -> None:
    sampler = FakeSampler(caps=capabilities(EnergySource.UNAVAILABLE))
    report = diagnose(client=FakeOllamaClient(), sampler=sampler)

    assert report.ok is False
    assert any("energy" in problem.lower() for problem in report.problems)


def test_partial_gpu_placement_is_reported(tmp_path: Path) -> None:
    client = FakeOllamaClient(size_bytes=2_000_000_000, size_vram_bytes=1_200_000_000)
    client.preload("llama3.2:3b-instruct-q4_K_M")
    report = diagnose(client=client, sampler=FakeSampler())

    assert report.ok is False
    assert any("60" in problem and "vram" in problem.lower() for problem in report.problems)


def test_the_json_report_is_sanitized_and_serializable() -> None:
    report = diagnose(client=FakeOllamaClient(), sampler=FakeSampler())
    payload = json.loads(json.dumps(report.to_dict()))

    assert payload["ok"] is True
    assert "gpu_fingerprint" in payload["gpu"]
    assert "uuid" not in json.dumps(payload).lower()


def test_the_doctor_command_exits_zero_on_a_healthy_host(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["doctor"], client=FakeOllamaClient(), sampler=FakeSampler())

    assert code == cli.EXIT_OK
    assert "ollama" in capsys.readouterr().out.lower()


def test_the_doctor_command_exits_three_on_a_broken_host(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sampler = FakeSampler(caps=capabilities(EnergySource.UNAVAILABLE))
    code = cli.main(["doctor"], client=FakeOllamaClient(), sampler=sampler)

    assert code == cli.EXIT_ENVIRONMENT
    assert capsys.readouterr().out


def test_the_doctor_json_flag_emits_only_json(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["doctor", "--json"], client=FakeOllamaClient(), sampler=FakeSampler())

    assert json.loads(capsys.readouterr().out)["ok"] is True


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


class CorrectAnswers(FakeOllamaClient):
    """A client whose answers satisfy the scored prompt's expectation."""

    def generate_stream(self, request):  # type: ignore[no-untyped-def]
        result = FakeOllamaClient.generate_stream(self, request)
        fields = {name: getattr(result, name) for name in result.__slots__}
        return type(result)(**{**fields, "text": "the answer is 3"})


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return run_experiment(
        build_config(tmp_path / "cfg", repetitions=3),
        client=FakeOllamaClient(),
        sampler=FakeSampler(),
    )


def test_a_report_writes_the_two_derived_artifacts(run_dir: Path) -> None:
    paths = build_report((run_dir,))

    assert paths.summaries == (run_dir / SUMMARY,)
    assert paths.reports == (run_dir / REPORT,)
    assert (run_dir / SUMMARY).is_file()
    assert (run_dir / REPORT).is_file()


def test_the_report_is_deterministic(run_dir: Path) -> None:
    """Regenerating a report must not change it; only raw data is authoritative."""
    build_report((run_dir,))
    first = (run_dir / REPORT).read_text(encoding="utf-8")
    second_summary = (run_dir / SUMMARY).read_text(encoding="utf-8")

    build_report((run_dir,))

    assert (run_dir / REPORT).read_text(encoding="utf-8") == first
    assert (run_dir / SUMMARY).read_text(encoding="utf-8") == second_summary


def test_the_summary_has_one_row_per_model_and_prompt(run_dir: Path) -> None:
    build_report((run_dir,))
    rows = list(csv.DictReader((run_dir / SUMMARY).read_text(encoding="utf-8").splitlines()))

    assert len(rows) == 3, "three prompts, one model"
    assert {row["prompt_id"] for row in rows} == {"short-01", "long-01", "scored-01"}
    assert all(int(row["repetitions"]) == 3 for row in rows)


def test_the_summary_reports_median_and_iqr(run_dir: Path) -> None:
    build_report((run_dir,))
    rows = list(csv.DictReader((run_dir / SUMMARY).read_text(encoding="utf-8").splitlines()))

    assert float(rows[0]["latency_median_s"]) == pytest.approx(2.0)
    assert float(rows[0]["latency_iqr_s"]) == pytest.approx(0.0)


def test_aggregate_ratios_are_totals_not_averages_of_ratios() -> None:
    """Averaging per-request ratios would weight a short request like a long one."""
    from llm_energy_bench.results import aggregate_ratio

    # 10 tokens in 1 s and 100 tokens in 100 s is 110/101, not (10 + 1)/2.
    assert aggregate_ratio([10, 100], [1.0, 100.0]) == pytest.approx(110 / 101)
    assert aggregate_ratio([], []) is None
    assert aggregate_ratio([10], [0.0]) is None


def test_prompts_are_weighted_equally_regardless_of_repetition_count() -> None:
    from llm_energy_bench.results import weighted_over_prompts

    # One prompt measured twice must not outweigh a prompt measured once.
    per_prompt = {"a": 10.0, "b": 20.0}
    assert weighted_over_prompts(per_prompt) == pytest.approx(15.0)
    assert weighted_over_prompts({}) is None


def test_the_quality_score_counts_only_scored_prompts(run_dir: Path) -> None:
    build_report((run_dir,))
    report = (run_dir / REPORT).read_text(encoding="utf-8")

    assert "Quality" in report
    # The fake answers "generated text", so the one scored prompt fails.
    assert "0%" in report or "0.0%" in report


def test_a_configuration_below_the_quality_floor_is_excluded_from_ranking(
    tmp_path: Path,
) -> None:
    run_dir = run_experiment(
        build_config(tmp_path / "cfg"), client=FakeOllamaClient(), sampler=FakeSampler()
    )
    build_report((run_dir,))
    report = (run_dir / REPORT).read_text(encoding="utf-8")

    assert "75%" in report
    assert "excluded" in report.lower() or "not eligible" in report.lower()


def test_a_configuration_above_the_quality_floor_is_ranked(tmp_path: Path) -> None:
    run_dir = run_experiment(
        build_config(tmp_path / "cfg"), client=CorrectAnswers(), sampler=FakeSampler()
    )
    build_report((run_dir,))
    report = (run_dir / REPORT).read_text(encoding="utf-8")

    assert "100" in report


def test_invalid_requests_are_excluded_from_aggregates_but_counted(tmp_path: Path) -> None:
    from llm_energy_bench.ollama import InvalidKind

    client = FakeOllamaClient(fail_on={"req-0001": InvalidKind.NO_OUTPUT})
    run_dir = run_experiment(build_config(tmp_path / "cfg"), client=client, sampler=FakeSampler())
    build_report((run_dir,))
    report = (run_dir / REPORT).read_text(encoding="utf-8")

    assert "1 invalid" in report or "invalid: 1" in report.lower()


def test_the_report_names_the_energy_source_and_its_caveat(run_dir: Path) -> None:
    build_report((run_dir,))
    report = (run_dir / REPORT).read_text(encoding="utf-8")

    assert "total_energy_counter" in report
    assert "GPU-only" in report, "a cost figure must never look like total cost of ownership"


def test_the_report_carries_no_private_data(run_dir: Path) -> None:
    build_report((run_dir,))

    assert "/home/" not in (run_dir / REPORT).read_text(encoding="utf-8")


def test_a_report_over_several_runs_compares_them(tmp_path: Path) -> None:
    first = run_experiment(
        build_config(tmp_path / "a"), client=FakeOllamaClient(), sampler=FakeSampler()
    )
    second = run_experiment(
        build_config(tmp_path / "b", host_id="host-b"),
        client=FakeOllamaClient(eval_count=240),
        sampler=FakeSampler(power=30.0),
    )

    paths = build_report((first, second))

    assert len(paths.summaries) == 2
    assert paths.comparison_markdown
    assert "host-a" in paths.comparison_markdown
    assert "host-b" in paths.comparison_markdown


def test_the_comparison_names_the_speed_and_energy_winners(tmp_path: Path) -> None:
    """Only configurations that clear the quality floor may be ranked at all."""
    fast_hungry = run_experiment(
        build_config(tmp_path / "a"),
        client=CorrectAnswers(eval_count=240),
        sampler=FakeSampler(caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION), power=90.0),
    )
    slow_frugal = run_experiment(
        build_config(tmp_path / "b", host_id="host-b"),
        client=CorrectAnswers(eval_count=120),
        sampler=FakeSampler(caps=capabilities(EnergySource.POWER_INSTANT_INTEGRATION), power=10.0),
    )

    comparison = build_report((fast_hungry, slow_frugal)).comparison_markdown

    assert "speed" in comparison.lower()
    assert "energy" in comparison.lower()
    assert "host-b" in comparison


def test_reporting_an_unvalidatable_run_is_an_error(tmp_path: Path) -> None:
    from llm_energy_bench.results import ResultsError

    empty = tmp_path / "not-a-run"
    empty.mkdir()

    with pytest.raises(ResultsError):
        build_report((empty,))


def test_the_report_command_writes_and_exits_zero(
    run_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["report", str(run_dir)])

    assert code == cli.EXIT_OK
    assert (run_dir / REPORT).is_file()
    assert str(run_dir.name) in capsys.readouterr().out


def test_the_report_command_reports_a_bad_run_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["report", str(tmp_path / "absent")])

    assert code == cli.EXIT_USAGE
    assert capsys.readouterr().err
