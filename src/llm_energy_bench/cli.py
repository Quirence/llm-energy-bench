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

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3
EXIT_RUN_FAILED = 4

PROGRAM = "python -m llm_energy_bench"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class UsageError(Exception):
    """The invocation itself is wrong: bad arguments, bad config contents."""


class PreflightError(Exception):
    """The host cannot support a valid measurement (no Ollama, no GPU, ...)."""


class RunFailedError(Exception):
    """Measurement started but could not complete."""


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report what this host can and cannot measure, without measuring anything."""
    from llm_energy_bench.config import ConfigError, load_config
    from llm_energy_bench.nvml import NvmlSampler
    from llm_energy_bench.ollama import OllamaClient
    from llm_energy_bench.results import diagnose

    config = None
    if getattr(args, "config", None) is not None:
        try:
            config = load_config(args.config)
        except ConfigError as error:
            raise UsageError(str(error)) from error

    client = getattr(args, "client", None)
    sampler = getattr(args, "sampler", None)
    owns = client is None
    if client is None:
        client = OllamaClient(config.ollama_url if config else DEFAULT_OLLAMA_URL)
    if sampler is None:
        sampler = NvmlSampler(gpu_index=config.gpu_index if config else 0)

    try:
        report = diagnose(client=client, sampler=sampler, config=config)
    finally:
        if owns:
            client.close()

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else report.render())
    return EXIT_OK if report.ok else EXIT_ENVIRONMENT


def cmd_run(args: argparse.Namespace) -> int:
    """Execute one experiment, then report how it ended."""
    from llm_energy_bench.config import ConfigError, load_config
    from llm_energy_bench.results import RunStatus, build_report, validate_run
    from llm_energy_bench.runner import PreflightFailed, run_experiment

    try:
        config = load_config(args.config)
    except ConfigError as error:
        raise UsageError(str(error)) from error

    try:
        run_dir = run_experiment(
            config,
            client=getattr(args, "client", None),
            sampler=getattr(args, "sampler", None),
        )
    except PreflightFailed as error:
        raise PreflightError(str(error)) from error

    report = validate_run(run_dir)
    print(f"run: {run_dir}")
    print(f"status: {report.status.value}")
    for problem in report.errors:
        print(f"  error: {problem}", file=sys.stderr)

    if report.status is RunStatus.COMPLETED:
        build_report((run_dir,))
        print(f"report: {run_dir / 'report.md'}")
        return EXIT_OK
    raise RunFailedError(f"the run ended as {report.status.value}; artifacts kept in {run_dir}")


def cmd_report(args: argparse.Namespace) -> int:
    """Rebuild derived reports from raw artifacts, without repeating inference."""
    from llm_energy_bench.results import ResultsError, build_report

    for run_dir in args.run_dirs:
        if not run_dir.is_dir():
            raise UsageError(f"run directory not found: {run_dir}")

    try:
        paths = build_report(tuple(args.run_dirs))
    except ResultsError as error:
        raise UsageError(str(error)) from error

    for summary, report in zip(paths.summaries, paths.reports, strict=True):
        print(f"{report.parent.name}: {summary.name}, {report.name}")
    if paths.comparison_markdown:
        print()
        print(paths.comparison_markdown)
    return EXIT_OK


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
    doctor.add_argument(
        "--config",
        type=Path,
        metavar="<experiment.toml>",
        help="Also check that this experiment's models are installed.",
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


def main(
    argv: Sequence[str] | None = None,
    *,
    client: object | None = None,
    sampler: object | None = None,
) -> int:
    """Run one command and return its exit code.

    ``client`` and ``sampler`` exist so tests can drive the commands without an
    Ollama server or an NVIDIA GPU; nothing else passes them.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or EXIT_USAGE)

    args.client = client
    args.sampler = sampler

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
