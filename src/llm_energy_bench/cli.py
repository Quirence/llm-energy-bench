"""Command parsing, user-facing errors, and exit codes.

The command shell owns exit-code policy for the whole tool. Commands return an
exit code; they never call ``sys.exit`` and never let a traceback reach the
user.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

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


def _not_implemented(component: str) -> Callable[[argparse.Namespace], int]:
    def command(_args: argparse.Namespace) -> int:
        raise PreflightError(f"{component} is not implemented yet")

    return command


def cmd_doctor(args: argparse.Namespace) -> int:
    return _not_implemented("doctor")(args)


def cmd_run(args: argparse.Namespace) -> int:
    return _not_implemented("run")(args)


def cmd_report(args: argparse.Namespace) -> int:
    return _not_implemented("report")(args)


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
