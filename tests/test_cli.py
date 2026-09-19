"""Tests for the command shell: parsing, exit codes, and user-facing errors."""

from __future__ import annotations

import pytest

from llm_energy_bench import cli


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


def test_commands_are_not_implemented_yet_but_do_not_crash(tmp_path) -> None:
    """Unimplemented commands report an environment failure, never a traceback."""
    assert cli.main(["doctor"]) == cli.EXIT_ENVIRONMENT


def test_keyboard_interrupt_maps_to_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setitem(cli.COMMANDS, "doctor", interrupt)
    assert cli.main(["doctor"]) == cli.EXIT_RUN_FAILED


def test_module_entrypoint_exposes_main() -> None:
    from llm_energy_bench import __main__

    assert __main__.main is cli.main
