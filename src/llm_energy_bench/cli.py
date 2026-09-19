"""Command parsing, user-facing errors, and exit codes.

The command shell owns exit-code policy for the whole tool. Commands return an
exit code; they never call ``sys.exit`` and never let a traceback reach the
user.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from llm_energy_bench.config import ConfigError, ExperimentConfig, load_config
from llm_energy_bench.nvml import EnergySource, NvmlError, NvmlSampler
from llm_energy_bench.ollama import ModelNotFound, OllamaClient, OllamaError
from llm_energy_bench.results import (
    ResultsError,
    assert_public_safe,
    build_report,
    scan_for_private_data,
    validate_run,
)
from llm_energy_bench.runner import RunnerError, RunnerPreflightError, run_experiment

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3
EXIT_RUN_FAILED = 4

PROGRAM = "python -m llm_energy_bench"


class UsageError(Exception):
    """The invocation itself is wrong: bad arguments, bad config contents."""


class PreflightError(Exception):
    """The host cannot support a valid measurement (no Ollama, no GPU, ...)."""


class RunFailedError(Exception):
    """Measurement started but could not complete."""


def doctor_environment(
    config: ExperimentConfig,
    *,
    client_factory: Any = None,
    sampler_factory: Any = None,
) -> dict[str, Any]:
    """Inspect the configured runtime, GPU, and model placement without a run."""
    client_builder = client_factory or OllamaClient
    sampler_builder = sampler_factory or NvmlSampler
    runtime: dict[str, Any] = {
        "name": "ollama",
        "available": False,
        "version": None,
        "error": None,
    }
    gpu: dict[str, Any] = {
        "available": False,
        "energy_source": EnergySource.UNAVAILABLE.value,
        "error": None,
    }
    models: list[dict[str, Any]] = []

    try:
        with client_builder(config.ollama_url) as client:
            try:
                runtime["version"] = client.version()
                runtime["available"] = True
            except OllamaError as error:
                runtime["error"] = _safe_error(error)

            if runtime["available"]:
                for model_name in config.models:
                    try:
                        running = client.preload(model_name)
                        record = running.to_dict()
                        record["requested"] = model_name
                        record["installed"] = True
                        record["error"] = None
                    except ModelNotFound as error:
                        record = {
                            "requested": model_name,
                            "installed": False,
                            "fully_on_gpu": False,
                            "error": _safe_error(error),
                        }
                    except OllamaError as error:
                        record = {
                            "requested": model_name,
                            "installed": None,
                            "fully_on_gpu": False,
                            "error": _safe_error(error),
                        }
                    models.append(record)
    except (OllamaError, OSError, ValueError) as error:
        runtime["error"] = _safe_error(error)

    try:
        with sampler_builder(
            gpu_index=config.gpu_index,
            interval_ms=config.telemetry_interval_ms,
        ) as sampler:
            capabilities = sampler.probe(config.gpu_index)
            gpu = {"available": True, **capabilities.to_dict(), "error": None}
    except (NvmlError, OSError, ValueError) as error:
        gpu["error"] = _safe_error(error)

    models_ok = len(models) == len(config.models) and all(
        model.get("installed") is True
        and model.get("fully_on_gpu") is True
        and bool(model.get("digest"))
        for model in models
    )
    report = {
        "schema_version": 1,
        "ok": (
            runtime["available"] is True
            and gpu.get("available") is True
            and gpu.get("energy_source") != EnergySource.UNAVAILABLE.value
            and models_ok
        ),
        "runtime": runtime,
        "gpu": gpu,
        "models": models,
        "controls": {
            "num_ctx": config.options.num_ctx,
            "kv_cache": config.options.kv_cache,
            "kv_cache_verification": "not_exposed_by_ollama_api",
            "concurrency": config.concurrency,
        },
    }
    report = _sanitize_payload(report)
    assert_public_safe(report)
    return report


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "pilot.toml"


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        config = load_config(_default_config_path())
    except ConfigError as error:
        raise UsageError(str(error)) from error

    report = doctor_environment(config)
    if args.json:
        print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    else:
        _print_doctor(report)
    return EXIT_OK if report["ok"] else EXIT_ENVIRONMENT


def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as error:
        raise UsageError(str(error)) from error

    try:
        run_dir = run_experiment(config)
    except RunnerPreflightError as error:
        raise PreflightError(str(error)) from error
    except RunnerError as error:
        raise RunFailedError(str(error)) from error

    print(run_dir)
    validation = validate_run(run_dir)
    if not validation.ok:
        for error in validation.errors:
            print(f"validation: {error}", file=sys.stderr)
        return EXIT_RUN_FAILED
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    try:
        paths = build_report(tuple(args.run_dirs))
    except ResultsError as error:
        raise RunFailedError(str(error)) from error
    print(paths.summary_csv)
    print(paths.report_markdown)
    return EXIT_OK if paths.validation_ok else EXIT_RUN_FAILED


def _safe_error(error: BaseException) -> str:
    detail = str(error) or type(error).__name__
    return "<redacted>" if scan_for_private_data(detail) else detail


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str) and scan_for_private_data(value):
        return "<redacted>"
    return value


def _print_doctor(report: dict[str, Any]) -> None:
    runtime = report["runtime"]
    gpu = report["gpu"]
    print(f"Ollama: {'ok' if runtime['available'] else 'unavailable'}")
    if runtime.get("version"):
        print(f"  version: {runtime['version']}")
    if runtime.get("error"):
        print(f"  error: {runtime['error']}")
    print(f"GPU/NVML: {'ok' if gpu.get('available') else 'unavailable'}")
    if gpu.get("name"):
        print(f"  device: {gpu['name']}")
        print(f"  energy source: {gpu['energy_source']}")
    if gpu.get("error"):
        print(f"  error: {gpu['error']}")
    for model in report["models"]:
        state = "fully on GPU" if model.get("fully_on_gpu") is True else "not ready"
        print(f"Model {model['requested']}: {state}")
        if model.get("error"):
            print(f"  error: {model['error']}")


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "doctor": cmd_doctor,
    "run": cmd_run,
    "report": cmd_report,
}


class _Parser(argparse.ArgumentParser):
    """Argparse exits with code 2 on error, which is already our usage code."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=PROGRAM,
        description="Measure local LLM inference performance and GPU energy use.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{doctor,run,report}")

    doctor = subparsers.add_parser(
        "doctor",
        help="Check Ollama, GPU, NVML capabilities, and model placement.",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Emit a sanitized machine-readable report instead of text.",
    )

    run = subparsers.add_parser("run", help="Execute a measured experiment.")
    run.add_argument(
        "--config",
        required=True,
        type=Path,
        metavar="<experiment.toml>",
        help="Experiment configuration file.",
    )

    report = subparsers.add_parser("report", help="Build reports from completed runs.")
    report.add_argument(
        "run_dirs",
        nargs="+",
        type=Path,
        metavar="<run-dir>",
        help="One or more completed run directories.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or EXIT_USAGE)

    if args.command is None:
        parser.print_usage(sys.stderr)
        print(f"{PROGRAM}: error: a command is required", file=sys.stderr)
        return EXIT_USAGE

    try:
        return COMMANDS[args.command](args)
    except UsageError as error:
        print(f"{PROGRAM}: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except PreflightError as error:
        print(f"{PROGRAM}: environment error: {error}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except (RunFailedError, KeyboardInterrupt) as error:
        detail = "interrupted by user" if isinstance(error, KeyboardInterrupt) else str(error)
        print(f"{PROGRAM}: run failed: {detail}", file=sys.stderr)
        return EXIT_RUN_FAILED
