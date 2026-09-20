"""Tests for the command shell: parsing, exit codes, and user-facing errors."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_energy_bench import cli
from llm_energy_bench.config import ConfigError
from llm_energy_bench.nvml import NvmlUnavailable
from llm_energy_bench.ollama import OllamaUnavailable
from llm_energy_bench.results import ResultsError


def test_exit_code_constants_are_fixed() -> None:
    assert cli.EXIT_OK == 0
    assert cli.EXIT_USAGE == 2
    assert cli.EXIT_ENVIRONMENT == 3
    assert cli.EXIT_RUN_FAILED == 4


def test_no_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == cli.EXIT_USAGE
    assert "usage:" in capsys.readouterr().err.lower()


def test_unknown_command_is_a_usage_error() -> None:
    assert cli.main(["teleport"]) == cli.EXIT_USAGE


def test_doctor_parses_without_arguments() -> None:
    args = cli.build_parser().parse_args(["doctor"])
    assert args.command == "doctor"
    assert args.json is False


def test_doctor_parses_json_flag() -> None:
    args = cli.build_parser().parse_args(["doctor", "--json"])
    assert args.json is True


def test_default_doctor_config_prefers_repository_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = tmp_path / "configs" / "pilot.toml"
    expected.parent.mkdir()
    expected.write_text("[experiment]\n", encoding="utf-8")
    installed_module = (
        tmp_path
        / ".venv"
        / "Lib"
        / "site-packages"
        / "llm_energy_bench"
        / "cli.py"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "__file__", str(installed_module))

    assert cli._default_config_path() == expected.resolve()


def test_run_requires_a_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run"]) == cli.EXIT_USAGE
    assert "--config" in capsys.readouterr().err


def test_run_parses_config_path(tmp_path) -> None:
    config = tmp_path / "experiment.toml"
    args = cli.build_parser().parse_args(["run", "--config", str(config)])
    assert args.command == "run"
    assert args.config == config


def test_report_requires_at_least_one_run_dir() -> None:
    assert cli.main(["report"]) == cli.EXIT_USAGE


def test_report_accepts_multiple_run_dirs(tmp_path) -> None:
    first = tmp_path / "run-a"
    second = tmp_path / "run-b"
    args = cli.build_parser().parse_args(["report", str(first), str(second)])
    assert args.run_dirs == [first, second]


@pytest.mark.parametrize("command", ["doctor", "run", "report"])
def test_every_command_is_registered(command: str) -> None:
    assert command in cli.COMMANDS


def test_doctor_command_emits_json_and_returns_report_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_default_config_path", lambda: Path("pilot.toml"))
    monkeypatch.setattr(cli, "load_config", lambda _path: object())
    monkeypatch.setattr(cli, "doctor_environment", lambda _config: {"ok": True, "gpu": {}})

    assert cli.main(["doctor", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_run_command_returns_validation_failure_without_hiding_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(cli, "load_config", lambda _path: object())
    monkeypatch.setattr(cli, "run_experiment", lambda _config: run_dir)
    monkeypatch.setattr(
        cli,
        "validate_run",
        lambda _path: SimpleNamespace(ok=False, errors=("invalid request",)),
    )

    assert cli.main(["run", "--config", str(tmp_path / "pilot.toml")]) == cli.EXIT_RUN_FAILED
    captured = capsys.readouterr()
    assert str(run_dir) in captured.out
    assert "invalid request" in captured.err


@pytest.mark.parametrize(
    "error",
    [OllamaUnavailable("connection refused"), NvmlUnavailable("NVML unavailable")],
)
def test_run_command_maps_known_preflight_failures_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda _path: object())

    def fail(_config: object) -> Path:
        raise error

    monkeypatch.setattr(cli, "run_experiment", fail)

    assert cli.main(["run", "--config", str(tmp_path / "pilot.toml")]) == 3
    captured = capsys.readouterr()
    assert str(error) in captured.err
    assert "Traceback" not in captured.err


def test_run_command_maps_prompt_contract_failure_to_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda _path: object())

    def fail(_config: object) -> Path:
        raise ConfigError("prompt file is malformed")

    monkeypatch.setattr(cli, "run_experiment", fail)

    assert cli.main(["run", "--config", str(tmp_path / "pilot.toml")]) == 2
    captured = capsys.readouterr()
    assert "prompt file is malformed" in captured.err
    assert "Traceback" not in captured.err


def test_run_command_maps_post_run_storage_failure_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(cli, "load_config", lambda _path: object())
    monkeypatch.setattr(cli, "run_experiment", lambda _config: run_dir)

    def fail(_path: Path) -> object:
        raise ResultsError("validation artifact is unreadable")

    monkeypatch.setattr(cli, "validate_run", fail)

    assert cli.main(["run", "--config", str(tmp_path / "pilot.toml")]) == 4
    captured = capsys.readouterr()
    assert str(run_dir) in captured.out
    assert "validation artifact is unreadable" in captured.err
    assert "Traceback" not in captured.err


def test_report_command_returns_validation_failure_after_writing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = SimpleNamespace(
        summary_csv=tmp_path / "summary.csv",
        report_markdown=tmp_path / "report.md",
        validation_ok=False,
    )
    monkeypatch.setattr(cli, "build_report", lambda _run_dirs: paths)

    assert cli.main(["report", str(tmp_path / "run")]) == cli.EXIT_RUN_FAILED
    captured = capsys.readouterr()
    assert str(paths.report_markdown) in captured.out


def test_keyboard_interrupt_maps_to_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setitem(cli.COMMANDS, "doctor", interrupt)
    assert cli.main(["doctor"]) == cli.EXIT_RUN_FAILED


def test_module_entrypoint_exposes_main() -> None:
    from llm_energy_bench import __main__

    assert __main__.main is cli.main
