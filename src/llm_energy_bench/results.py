"""Immutable run artifacts: atomic writes, integrity checks, and privacy rules.

Raw request and telemetry data are authoritative; reports are derived and may
be regenerated at any time. That ordering drives every choice here.

* Nothing is buffered. Each record reaches disk as it is produced, so a run
  killed halfway through is still auditable rather than lost.
* Nothing is overwritten. Whole-file artifacts are written to a temporary file
  and renamed, so a crash mid-write cannot replace a good artifact with half
  of a new one, and a retry always receives a new run directory.
* Nothing private is published. Run artifacts are committed to a public
  repository, so a manifest carrying a home directory or a GPU UUID is rejected
  before it is written, not scrubbed afterwards.
"""

from __future__ import annotations

import csv
import getpass
import gzip
import hashlib
import io
import json
import os
import re
import secrets
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any

MAX_ARTIFACT_BYTES = 25 * 1024 * 1024

MANIFEST = "manifest.json"
RESOLVED_CONFIG = "config.resolved.toml"
WARMUPS = "warmups.jsonl"
REQUESTS = "requests.jsonl"
OUTPUTS = "outputs.jsonl"
TELEMETRY = "telemetry.jsonl.gz"
VALIDATION = "validation.json"
SUMMARY = "summary.csv"
REPORT = "report.md"

REQUIRED_RAW_ARTIFACTS = (MANIFEST, RESOLVED_CONFIG, REQUESTS, OUTPUTS, TELEMETRY)
DERIVED_ARTIFACTS = (VALIDATION, SUMMARY, REPORT)
RUN_ARTIFACTS = REQUIRED_RAW_ARTIFACTS + (WARMUPS,) + DERIVED_ARTIFACTS

_ENCODING = "utf-8"


class ResultsError(Exception):
    """An artifact could not be written, read, or trusted."""


class PrivacyError(ResultsError):
    """A payload carries data that must not reach a public artifact."""


class RunStatus(StrEnum):
    """How a run ended. An unfinished run keeps its data and says so."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReportPaths:
    """Derived report artifacts and their aggregate validation status."""

    summary_csv: Path
    report_markdown: Path
    validation_ok: bool


def build_report(run_dirs: tuple[Path, ...]) -> ReportPaths:
    """Validate raw runs and generate deterministic CSV and Markdown summaries."""
    if not run_dirs:
        raise ResultsError("at least one run directory is required")

    resolved = tuple(Path(run_dir) for run_dir in run_dirs)
    validations = tuple(validate_run(run_dir) for run_dir in resolved)
    for validation in validations:
        write_json(validation.run_dir / VALIDATION, validation.to_dict())

    records: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    for run_dir, validation in zip(resolved, validations, strict=True):
        try:
            manifest = json.loads((run_dir / MANIFEST).read_text(encoding=_ENCODING))
        except (OSError, json.JSONDecodeError) as error:
            raise ResultsError(f"{run_dir.name}/{MANIFEST} could not be read: {error}") from error
        if not isinstance(manifest, dict):
            raise ResultsError(f"{run_dir.name}/{MANIFEST} must contain a JSON object")
        run_id = str(manifest.get("run_id") or run_dir.name)
        manifests[run_id] = manifest
        if not validation.ok:
            continue
        for record in read_jsonl(run_dir / OUTPUTS):
            if record.get("valid") is True and isinstance(record.get("metrics"), dict):
                records.append({"run_id": run_id, **record})

    rows = _aggregate_report_rows(records, manifests)
    _assign_ranks(rows)

    summary_path = resolved[0] / SUMMARY
    report_path = resolved[0] / REPORT
    write_text(summary_path, _render_summary_csv(rows))
    write_text(report_path, _render_report(rows, validations))
    return ReportPaths(
        summary_csv=summary_path,
        report_markdown=report_path,
        validation_ok=all(validation.ok for validation in validations),
    )


_SUMMARY_FIELDS = (
    "run_id",
    "host_id",
    "model",
    "model_digest",
    "prompt_category",
    "request_count",
    "latency_median_seconds",
    "latency_iqr_seconds",
    "ttft_median_seconds",
    "ttft_iqr_seconds",
    "prompt_tokens",
    "uncached_prompt_tokens",
    "output_tokens",
    "prefill_tokens_per_second",
    "decode_tokens_per_second",
    "average_gpu_power_median_watts",
    "observed_peak_gpu_power_max_watts",
    "gpu_energy_joules",
    "joules_per_output_token",
    "end_to_end_tokens_per_second",
    "output_tokens_per_joule",
    "gpu_cost_per_million_output_tokens",
    "cost_currency",
    "energy_source",
    "temperature_start_median_c",
    "temperature_peak_max_c",
    "power_limit_median_watts",
    "vram_start_median_bytes",
    "vram_peak_max_bytes",
    "quality_score",
    "ranking_eligible",
    "speed_rank",
    "energy_rank",
)


def _aggregate_report_rows(
    records: list[dict[str, Any]], manifests: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    quality: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for record in records:
        run_id = str(record["run_id"])
        model = str(record.get("model") or "unknown")
        digest = str(record.get("model_digest") or "unknown")
        category = str(record.get("prompt_category") or "unknown")
        grouped[(run_id, model, digest, category)].append(record)
        score = _number(record["metrics"].get("quality_score"))
        prompt_id = record.get("prompt_id")
        if score is not None and isinstance(prompt_id, str):
            quality[(run_id, model, digest)][prompt_id].append(score)

    config_quality = {
        key: statistics.fmean(statistics.fmean(scores) for scores in by_prompt.values())
        for key, by_prompt in quality.items()
        if by_prompt
    }
    rows: list[dict[str, Any]] = []
    for key in sorted(grouped):
        run_id, model, digest, category = key
        group = grouped[key]
        metrics = [record["metrics"] for record in group]
        latencies = _numbers(item.get("latency_seconds") for item in metrics)
        ttfts = _numbers(item.get("ttft_seconds") for item in metrics)
        tokens = _numbers(item.get("output_tokens") for item in metrics)
        prompt_tokens = _numbers(
            item.get("prompt_tokens", record.get("prompt_eval_count"))
            for record, item in zip(group, metrics, strict=True)
        )
        uncached_prompt_tokens = _numbers(
            item.get(
                "uncached_prompt_tokens",
                item.get("prompt_tokens", record.get("prompt_eval_count")),
            )
            for record, item in zip(group, metrics, strict=True)
        )
        prompt_durations = _numbers(record.get("prompt_eval_duration_ns") for record in group)
        decode_durations = _numbers(record.get("eval_duration_ns") for record in group)
        average_power = _numbers(item.get("average_gpu_power_watts") for item in metrics)
        peak_power = _numbers(item.get("observed_peak_gpu_power_watts") for item in metrics)
        energies = _numbers(item.get("gpu_energy_joules") for item in metrics)
        costs = [
            (cost, tokens_for_request)
            for item in metrics
            if (cost := _number(item.get("gpu_cost_per_million_output_tokens"))) is not None
            and (tokens_for_request := _number(item.get("output_tokens"))) is not None
        ]
        currencies = _strings(item.get("cost_currency") for item in metrics)
        energy_sources = _strings(item.get("energy_source") for item in metrics)
        temperature_start = _numbers(item.get("temperature_start_c") for item in metrics)
        temperature_peak = _numbers(item.get("temperature_peak_c") for item in metrics)
        power_limits = _numbers(item.get("power_limit_watts") for item in metrics)
        vram_start = _numbers(item.get("vram_start_bytes") for item in metrics)
        vram_peak = _numbers(item.get("vram_peak_bytes") for item in metrics)
        total_latency = sum(latencies)
        total_tokens = sum(tokens)
        total_prompt_tokens = sum(prompt_tokens)
        total_uncached_prompt_tokens = sum(uncached_prompt_tokens)
        total_energy = sum(energies)
        score = config_quality.get((run_id, model, digest))
        manifest = manifests.get(run_id, {})
        rows.append(
            {
                "run_id": run_id,
                "host_id": str(manifest.get("host_id") or "unknown"),
                "model": model,
                "model_digest": digest,
                "prompt_category": category,
                "request_count": len(group),
                "latency_median_seconds": _median(latencies),
                "latency_iqr_seconds": _iqr(latencies),
                "ttft_median_seconds": _median(ttfts),
                "ttft_iqr_seconds": _iqr(ttfts),
                "prompt_tokens": total_prompt_tokens,
                "uncached_prompt_tokens": total_uncached_prompt_tokens,
                "output_tokens": total_tokens,
                "prefill_tokens_per_second": _safe_ratio(
                    total_uncached_prompt_tokens, sum(prompt_durations) / 1e9
                ),
                "decode_tokens_per_second": _safe_ratio(total_tokens, sum(decode_durations) / 1e9),
                "average_gpu_power_median_watts": _median(average_power),
                "observed_peak_gpu_power_max_watts": _maximum(peak_power),
                "gpu_energy_joules": total_energy,
                "joules_per_output_token": _safe_ratio(total_energy, total_tokens),
                "end_to_end_tokens_per_second": _safe_ratio(total_tokens, total_latency),
                "output_tokens_per_joule": _safe_ratio(total_tokens, total_energy),
                "gpu_cost_per_million_output_tokens": _weighted_average(costs),
                "cost_currency": _one_or_joined(currencies),
                "energy_source": _one_or_joined(energy_sources),
                "temperature_start_median_c": _median(temperature_start),
                "temperature_peak_max_c": _maximum(temperature_peak),
                "power_limit_median_watts": _median(power_limits),
                "vram_start_median_bytes": _median(vram_start),
                "vram_peak_max_bytes": _maximum(vram_peak),
                "quality_score": score,
                "ranking_eligible": score is not None and score >= 0.75,
                "speed_rank": None,
                "energy_rank": None,
            }
        )
    return rows


def _assign_ranks(rows: list[dict[str, Any]]) -> None:
    blocks = sorted({(str(row["host_id"]), str(row["prompt_category"])) for row in rows})
    for host_id, category in blocks:
        eligible = [
            row
            for row in rows
            if row["host_id"] == host_id
            and row["prompt_category"] == category
            and row["ranking_eligible"]
        ]
        speed = sorted(
            eligible,
            key=lambda row: (
                -float(row["end_to_end_tokens_per_second"] or 0),
                str(row["run_id"]),
                str(row["model"]),
            ),
        )
        energy = sorted(
            eligible,
            key=lambda row: (
                -float(row["output_tokens_per_joule"] or 0),
                str(row["run_id"]),
                str(row["model"]),
            ),
        )
        for rank, row in enumerate(speed, start=1):
            row["speed_rank"] = rank
        for rank, row in enumerate(energy, start=1):
            row["energy_rank"] = rank


def _render_summary_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_SUMMARY_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _csv_value(row.get(name)) for name in _SUMMARY_FIELDS})
    return buffer.getvalue()


def _render_report(rows: list[dict[str, Any]], validations: tuple[ValidationReport, ...]) -> str:
    valid_count = sum(validation.ok for validation in validations)
    inversions = [
        row
        for row in rows
        if row["speed_rank"] is not None and row["speed_rank"] != row["energy_rank"]
    ]
    lines = [
        "# LLM energy benchmark report",
        "",
        f"Validated runs: {valid_count}/{len(validations)}.",
        "",
    ]
    if not rows:
        lines.extend(
            [
                "No validated run contributed aggregate measurements.",
                "Fix validation errors before interpreting performance or energy rankings.",
                "",
            ]
        )
    elif inversions:
        lines.extend(
            [
                "Speed and energy rankings differ in at least one aggregate workload block.",
                "This is descriptive only; statistical rank-inversion criteria are "
                "evaluated separately.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Speed and energy rankings agree in the observed aggregates.",
                "This does not establish equivalence outside the measured configurations.",
                "",
            ]
        )
    lines.extend(
        [
            "| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | "
            "Speed rank | Energy rank |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            "| {run_id} | {host_id} | {model} | {prompt_category} | {request_count} | "
            "{end_to_end_tokens_per_second} | {output_tokens_per_joule} | {quality_score} | "
            "{speed_rank} | {energy_rank} |".format(
                **{key: _csv_value(value) for key, value in row.items()}
            )
        )
    lines.extend(["", "GPU energy and cost figures are GPU-only estimates, not wall energy.", ""])
    return "\n".join(lines)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _numbers(values: Any) -> list[float]:
    return [number for value in values if (number := _number(value)) is not None]


def _strings(values: Any) -> list[str]:
    return [value for value in values if isinstance(value, str) and value]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _maximum(values: list[float]) -> float | None:
    return max(values) if values else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _iqr(values: list[float]) -> float | None:
    lower = _percentile(values, 0.25)
    upper = _percentile(values, 0.75)
    return None if lower is None or upper is None else upper - lower


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def _weighted_average(values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in values) / total_weight


def _one_or_joined(values: list[str]) -> str | None:
    unique = sorted(set(values))
    return "|".join(unique) if unique else None


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return format(value, ".12g")
    return value


# --------------------------------------------------------------------------
# Atomic whole-file writes
# --------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> None:
    """Serialize ``payload`` and replace ``path`` atomically.

    Keys are sorted so that equal payloads hash equally, which is what lets a
    manifest checksum mean something.
    """
    try:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    except (TypeError, ValueError) as error:
        raise ResultsError(f"{path.name} is not JSON-serializable: {error}") from error
    write_text(path, text)


def write_text(path: Path, text: str) -> None:
    """Replace ``path`` atomically, leaving the previous content intact on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("w", encoding=_ENCODING, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ResultsError(f"{path.name} could not be written: {error}") from error


# --------------------------------------------------------------------------
# Append-only record streams
# --------------------------------------------------------------------------


class JsonlWriter:
    """Append-only JSONL, flushed per record so an interrupted run keeps its data."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("a", encoding=_ENCODING, newline="\n")

    def write(self, record: Any) -> None:
        try:
            line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise ResultsError(f"{self.path.name}: record is not serializable: {error}") from error
        self._handle.write(line + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            self._handle.close()

    def __enter__(self) -> JsonlWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class GzipJsonlWriter:
    """Append-only gzip-compressed JSONL for telemetry.

    Each record is followed by a zlib sync flush. That costs a little
    compression ratio and buys the property that matters more: if the process
    dies before the gzip trailer is written, every record already produced can
    still be recovered.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # The writer owns this handle for the life of a request and is itself a
        # context manager, so SIM115 does not apply.
        self._handle = gzip.open(path, "at", encoding=_ENCODING, newline="\n")  # noqa: SIM115

    def write(self, record: Any) -> None:
        try:
            line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise ResultsError(f"{self.path.name}: record is not serializable: {error}") from error
        self._handle.write(line + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> GzipJsonlWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    """Read a JSONL artifact, naming the offending line if one is malformed."""
    try:
        text = path.read_text(encoding=_ENCODING)
    except OSError as error:
        raise ResultsError(f"{path.name} could not be read: {error}") from error
    return _decode_jsonl(text, path.name)


def read_gzip_jsonl(path: Path, tolerate_truncation: bool = False) -> tuple[dict[str, Any], ...]:
    """Read a gzip JSONL artifact.

    ``tolerate_truncation`` recovers the records of an interrupted run, whose
    file legitimately has no gzip trailer. It is off by default so that a
    truncated file in a supposedly complete run is not mistaken for a valid one.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ResultsError(f"{path.name} could not be read: {error}") from error

    try:
        text = gzip.decompress(raw).decode(_ENCODING)
    except (OSError, EOFError, gzip.BadGzipFile) as error:
        if not tolerate_truncation:
            raise ResultsError(
                f"{path.name} is truncated or corrupt: {error}; "
                "pass tolerate_truncation=True to recover an interrupted run"
            ) from error
        text = _decompress_partial(raw)

    return _decode_jsonl(text, path.name, drop_incomplete_tail=tolerate_truncation)


def _decompress_partial(raw: bytes) -> str:
    """Decompress as much of a truncated gzip stream as the data allows."""
    import zlib

    decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16)
    try:
        data = decompressor.decompress(raw)
    except zlib.error as error:
        raise ResultsError(f"gzip stream is unrecoverable: {error}") from error
    return data.decode(_ENCODING, errors="ignore")


def _decode_jsonl(
    text: str, file_name: str, drop_incomplete_tail: bool = False
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            # A partially flushed final line is expected in an interrupted run.
            if drop_incomplete_tail and number == len(lines) and not text.endswith("\n"):
                break
            raise ResultsError(f"{file_name} line {number}: not valid JSON: {error.msg}") from error
        if not isinstance(record, dict):
            raise ResultsError(f"{file_name} line {number}: expected a JSON object")
        records.append(record)
    return tuple(records)


# --------------------------------------------------------------------------
# Checksums
# --------------------------------------------------------------------------


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ResultsError(f"{path.name} could not be hashed: {error}") from error
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------

_PRIVATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a Windows user directory", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+", re.IGNORECASE)),
    ("a Windows absolute path", re.compile(r"\b[A-Za-z]:\\")),
    ("a POSIX home directory", re.compile(r"/(?:home|Users)/[^/\s]+")),
    (
        "URL credentials",
        re.compile(r"https?://[^\s/@:]+(?::[^\s/@]*)?@", re.IGNORECASE),
    ),
    ("a raw GPU UUID", re.compile(r"\bGPU-[0-9a-f]{8}-", re.IGNORECASE)),
    ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}")),
    ("a GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}")),
    ("an API key", re.compile(r"\bsk-[A-Za-z0-9-]{8,}")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


def scan_for_private_data(value: str) -> tuple[str, ...]:
    """Return a description of everything private found in ``value``."""
    found = [label for label, pattern in _PRIVATE_PATTERNS if pattern.search(value)]

    user = _current_username()
    if user and re.search(rf"\b{re.escape(user)}\b", value):
        found.append("the current username")
    return tuple(found)


def _current_username() -> str | None:
    """The account running the benchmark, which must not appear in artifacts."""
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - getuser can fail without a passwd entry
        return None
    # A very short name would match far too much ordinary text.
    return user if len(user) >= 3 else None


def assert_public_safe(payload: Any, path: str = "") -> None:
    """Reject a payload that must not be published, naming where the problem is.

    This runs before an artifact is written rather than after. Scrubbing a
    finished manifest would leave the question of what else was missed; refusing
    to write it keeps the failure loud and local.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            location = f"{path}.{key}" if path else str(key)
            _check_scalar(str(key), location)
            assert_public_safe(value, location)
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_public_safe(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        _check_scalar(payload, path or "<value>")


def _check_scalar(value: str, location: str) -> None:
    found = scan_for_private_data(value)
    if found:
        raise PrivacyError(
            f"{location} contains {', '.join(found)}; public artifacts must not carry it"
        )


# --------------------------------------------------------------------------
# Run directories
# --------------------------------------------------------------------------


def create_run_dir(output_dir: Path, experiment_id: str, host_id: str) -> Path:
    """Create a fresh run directory.

    A run is never resumed in place: a retry receives a new identifier, so an
    earlier interrupted run keeps its artifacts and stays auditable.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(100):
        run_dir = output_dir / f"{experiment_id}-{host_id}-{stamp}-{secrets.token_hex(3)}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        except OSError as error:
            raise ResultsError(f"run directory could not be created: {error}") from error
        return run_dir
    raise ResultsError("could not allocate a unique run directory")  # pragma: no cover


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The auditable verdict on one run directory."""

    run_dir: Path
    status: RunStatus
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    sizes: dict[str, int]
    checksums: dict[str, str]
    record_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_dir.name,
            "status": self.status.value,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "sizes": dict(self.sizes),
            "checksums": dict(self.checksums),
            "record_counts": dict(self.record_counts),
        }


def validate_run(run_dir: Path) -> ValidationReport:
    """Check one run directory for completeness, size, and readability."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ResultsError(f"run directory not found: {run_dir}")

    errors: list[str] = []
    warnings: list[str] = []
    sizes: dict[str, int] = {}
    checksums: dict[str, str] = {}
    counts: dict[str, int] = {}

    for name in RUN_ARTIFACTS:
        # validation.json is this function's own derived output. Hashing or
        # sizing it inside itself makes every otherwise identical validation
        # rewrite produce a different payload.
        if name == VALIDATION:
            continue
        path = run_dir / name
        if not path.is_file():
            if name in REQUIRED_RAW_ARTIFACTS:
                errors.append(f"{name} is missing")
            else:
                warnings.append(f"{name} has not been generated yet")
            continue

        size = path.stat().st_size
        sizes[name] = size
        checksums[name] = sha256_file(path)
        if size > MAX_ARTIFACT_BYTES:
            errors.append(f"{name} is {size / 1024 / 1024:.1f} MB, above the 25 MB artifact limit")
        if size == 0 and name in REQUIRED_RAW_ARTIFACTS:
            errors.append(f"{name} is empty")

    status = _read_status(run_dir, errors)
    _count_records(run_dir, counts, errors, tolerate_truncation=status is not RunStatus.COMPLETED)

    if status is RunStatus.COMPLETED and not errors:
        _cross_check_counts(counts, warnings)
        _validate_completed_schema(run_dir, counts, checksums, errors)
    elif status is not RunStatus.COMPLETED:
        warnings.append(f"the run ended with status {status.value}; its data is partial")

    return ValidationReport(
        run_dir=run_dir,
        status=status,
        ok=not errors and status is RunStatus.COMPLETED,
        errors=tuple(errors),
        warnings=tuple(warnings),
        sizes=sizes,
        checksums=checksums,
        record_counts=counts,
    )


def _read_status(run_dir: Path, errors: list[str]) -> RunStatus:
    path = run_dir / MANIFEST
    if not path.is_file():
        return RunStatus.FAILED
    try:
        manifest = json.loads(path.read_text(encoding=_ENCODING))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{MANIFEST} is not readable: {error}")
        return RunStatus.FAILED

    raw = manifest.get("status")
    try:
        return RunStatus(raw)
    except ValueError:
        errors.append(f"{MANIFEST} has an unknown status {raw!r}")
        return RunStatus.FAILED


def _count_records(
    run_dir: Path, counts: dict[str, int], errors: list[str], tolerate_truncation: bool
) -> None:
    for name in (WARMUPS, REQUESTS, OUTPUTS):
        path = run_dir / name
        if path.is_file():
            try:
                counts[name] = len(read_jsonl(path))
            except ResultsError as error:
                errors.append(str(error))

    telemetry = run_dir / TELEMETRY
    if telemetry.is_file():
        try:
            counts[TELEMETRY] = len(read_gzip_jsonl(telemetry, tolerate_truncation))
        except ResultsError as error:
            errors.append(str(error))


def _cross_check_counts(counts: dict[str, int], warnings: list[str]) -> None:
    requests = counts.get(REQUESTS)
    outputs = counts.get(OUTPUTS)
    if requests is not None and outputs is not None and requests != outputs:
        warnings.append(f"{REQUESTS} holds {requests} records but {OUTPUTS} holds {outputs}")
    if counts.get(TELEMETRY) == 0:
        warnings.append(f"{TELEMETRY} holds no samples")


def _validate_schema_v1(run_dir: Path, errors: list[str]) -> None:
    """Validate the original schema-v1 zero-cache measurement contract."""
    try:
        manifest = json.loads((run_dir / MANIFEST).read_text(encoding=_ENCODING))
    except (OSError, json.JSONDecodeError):
        return  # The structural validation above already reports this.
    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        errors.append(f"{MANIFEST} schema v1 has no model records")
        return

    expected_digests: dict[str, str] = {}
    for model in models:
        if not isinstance(model, dict):
            errors.append(f"{MANIFEST} schema v1 contains a malformed model record")
            continue
        name = model.get("name")
        digest = model.get("digest")
        if model.get("fully_on_gpu") is not True:
            errors.append(f"model {name!r} is not confirmed fully on GPU")
        if isinstance(name, str) and isinstance(digest, str) and digest:
            expected_digests[name] = digest

    try:
        requests = read_jsonl(run_dir / REQUESTS)
        outputs = read_jsonl(run_dir / OUTPUTS)
        telemetry = read_gzip_jsonl(run_dir / TELEMETRY)
    except ResultsError:
        return  # The structural validation already includes the read failure.

    request_ids = [record.get("request_id") for record in requests]
    output_ids = [record.get("request_id") for record in outputs]
    if len(request_ids) != len(set(request_ids)):
        errors.append(f"{REQUESTS} contains duplicate request IDs")
    if set(request_ids) != set(output_ids):
        errors.append(f"{REQUESTS} and {OUTPUTS} do not describe the same request IDs")

    telemetry_times: dict[str, list[float]] = {}
    for record in telemetry:
        request_id = record.get("request_id")
        timestamp = record.get("monotonic_s")
        if isinstance(request_id, str) and isinstance(timestamp, int | float):
            telemetry_times.setdefault(request_id, []).append(float(timestamp))

    for output in outputs:
        request_id = output.get("request_id")
        label = repr(request_id)
        if output.get("valid") is not True:
            errors.append(f"request {label} is invalid for primary analysis")

        model_name = output.get("model")
        expected_digest = expected_digests.get(model_name)
        if expected_digest is None or output.get("model_digest") != expected_digest:
            errors.append(f"request {label} model digest does not match the manifest")

        cached = output.get("prompt_eval_cached_count")
        if isinstance(cached, int) and not isinstance(cached, bool) and cached > 0:
            errors.append(f"request {label} used {cached} cached prompt tokens")

        metrics = output.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"request {label} has no derived metrics")
            continue
        energy = metrics.get("gpu_energy_joules")
        if not isinstance(energy, int | float) or isinstance(energy, bool) or energy <= 0:
            errors.append(f"request {label} has no positive GPU energy")
        gap = metrics.get("max_telemetry_gap_seconds")
        if isinstance(gap, int | float) and not isinstance(gap, bool) and gap > 0.5:
            errors.append(f"request {label} has a telemetry gap above 500 ms")

        times = sorted(telemetry_times.get(request_id, []))
        if len(times) < 2:
            errors.append(f"request {label} has no telemetry coverage")
        elif any(right - left > 0.5 for left, right in zip(times, times[1:], strict=False)):
            errors.append(f"request {label} raw telemetry has a gap above 500 ms")


def _validate_completed_schema(
    run_dir: Path,
    counts: dict[str, int],
    checksums: dict[str, str],
    errors: list[str],
) -> None:
    try:
        manifest = json.loads((run_dir / MANIFEST).read_text(encoding=_ENCODING))
    except (OSError, json.JSONDecodeError):
        return
    schema = manifest.get("schema_version")
    if schema == 1:
        _validate_schema_v1(run_dir, errors)
    elif schema == 2:
        _validate_schema_v2(run_dir, manifest, counts, checksums, errors)
    else:
        errors.append(f"{MANIFEST} has unsupported schema_version {schema!r}")


def _validate_schema_v2(
    run_dir: Path,
    manifest: dict[str, Any],
    counts: dict[str, int],
    checksums: dict[str, str],
    errors: list[str],
) -> None:
    """Validate the auditable warm-cache schema-v2 contract independently."""
    if manifest.get("prompt_cache_policy") != "template_floor_v2":
        errors.append(f"{MANIFEST} schema v2 has no recognized prompt cache policy")
    if manifest.get("cache_buster_policy") not in {
        "uuid_prefix_v1",
        "uuid_slot_prefix_v2",
        "uuid_slot_prefix_v3",
        "uuid_stable_slot_prefix_v4",
    }:
        errors.append(f"{MANIFEST} schema v2 has no recognized cache buster policy")
    if manifest.get("max_cache_excess_tokens") != 1:
        errors.append(f"{MANIFEST} schema v2 has an unexpected cache excess limit")
    if manifest.get("max_measured_load_duration_ns") != 100_000_000:
        errors.append(f"{MANIFEST} schema v2 has an unexpected model reload threshold")

    for name in (WARMUPS, REQUESTS, OUTPUTS, TELEMETRY):
        if not (run_dir / name).is_file():
            errors.append(f"{name} is required by schema v2")

    declared_hashes = manifest.get("artifact_sha256")
    expected_hashed = (RESOLVED_CONFIG, WARMUPS, REQUESTS, OUTPUTS, TELEMETRY)
    if not isinstance(declared_hashes, dict):
        errors.append(f"{MANIFEST} schema v2 has no artifact checksums")
    else:
        for name in expected_hashed:
            declared = declared_hashes.get(name)
            actual = checksums.get(name)
            if not isinstance(declared, str) or declared != actual:
                errors.append(f"{name} checksum does not match {MANIFEST}")
    if manifest.get("config_sha256") != checksums.get(RESOLVED_CONFIG):
        errors.append(f"{RESOLVED_CONFIG} checksum does not match config_sha256")

    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        errors.append(f"{MANIFEST} schema v2 has no model records")
        return
    controls = manifest.get("controls")
    if not isinstance(controls, dict):
        errors.append(f"{MANIFEST} schema v2 has no controls")
        return
    runtime = manifest.get("runtime")
    expected_runtime = controls.get("expected_runtime_version")
    if not isinstance(expected_runtime, str) or not expected_runtime:
        errors.append(f"{MANIFEST} schema v2 has no frozen runtime version")
    elif not isinstance(runtime, dict) or runtime.get("version") != expected_runtime:
        errors.append("runtime version does not match the frozen control")
    expected_control_digests = controls.get("expected_model_digests")
    if not isinstance(expected_control_digests, dict):
        errors.append(f"{MANIFEST} schema v2 has no frozen model digests")
        expected_control_digests = {}

    expected_digests: dict[str, str] = {}
    expected_cache_floors: dict[str, int] = {}
    manifest_model_names: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            errors.append(f"{MANIFEST} schema v2 contains a malformed model record")
            continue
        name = model.get("name")
        digest = model.get("digest")
        floor = model.get("template_cache_baseline_tokens")
        if model.get("fully_on_gpu") is not True:
            errors.append(f"model {name!r} is not confirmed fully on GPU")
        if not isinstance(name, str) or not isinstance(digest, str) or not digest:
            errors.append(f"{MANIFEST} schema v2 contains an unidentified model")
            continue
        manifest_model_names.append(name)
        expected_digests[name] = digest
        if expected_control_digests.get(name) != digest:
            errors.append(f"model {name!r} digest does not match the frozen control")
        if isinstance(floor, int) and not isinstance(floor, bool) and floor >= 0:
            expected_cache_floors[name] = floor
        else:
            errors.append(f"model {name!r} has no valid template cache floor")
    configured_models = controls.get("models")
    exact_names = (
        len(manifest_model_names) == len(set(manifest_model_names))
        and isinstance(configured_models, list)
        and configured_models == manifest_model_names
        and set(expected_control_digests) == set(manifest_model_names)
    )
    if not exact_names:
        errors.append(f"{MANIFEST} schema v2 has inconsistent frozen model digest coverage")

    try:
        warmups = read_jsonl(run_dir / WARMUPS)
        requests = read_jsonl(run_dir / REQUESTS)
        outputs = read_jsonl(run_dir / OUTPUTS)
        telemetry = read_gzip_jsonl(run_dir / TELEMETRY)
    except ResultsError:
        return

    expected_request_count = _expected_request_count(manifest)
    if expected_request_count is None:
        errors.append(f"{MANIFEST} schema v2 has invalid campaign counts")
    else:
        for name in (REQUESTS, OUTPUTS):
            if counts.get(name) != expected_request_count:
                errors.append(
                    f"{name} has {counts.get(name)} records; expected "
                    f"{expected_request_count} measured requests"
                )
        for counter in ("started_requests", "completed_requests", "valid_requests"):
            if manifest.get(counter) != expected_request_count:
                errors.append(f"{MANIFEST} {counter} does not match expected request count")
    expected_warmups = controls.get("warmup_requests")
    if isinstance(expected_warmups, int) and not isinstance(expected_warmups, bool):
        expected_warmup_count = expected_warmups * len(models)
        if counts.get(WARMUPS) != expected_warmup_count:
            errors.append(f"{WARMUPS} does not contain the expected warm-up count")
        if manifest.get("completed_warmups") != expected_warmup_count:
            errors.append(f"{MANIFEST} completed_warmups does not match raw warm-ups")
    else:
        errors.append(f"{MANIFEST} schema v2 has no valid warmup_requests control")

    _validate_warmup_floors(warmups, expected_digests, expected_cache_floors, errors)
    _validate_measured_records(
        requests, outputs, telemetry, expected_digests, expected_cache_floors, errors
    )


def _expected_request_count(manifest: dict[str, Any]) -> int | None:
    prompt_count = manifest.get("prompt_count")
    repetitions = manifest.get("repetitions")
    models = manifest.get("models")
    if (
        isinstance(prompt_count, int)
        and not isinstance(prompt_count, bool)
        and prompt_count > 0
        and isinstance(repetitions, int)
        and not isinstance(repetitions, bool)
        and repetitions > 0
        and isinstance(models, list)
        and models
    ):
        return prompt_count * repetitions * len(models)
    return None


def _validate_warmup_floors(
    warmups: tuple[dict[str, Any], ...],
    expected_digests: dict[str, str],
    expected_floors: dict[str, int],
    errors: list[str],
) -> None:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in warmups:
        model = record.get("model")
        if isinstance(model, str):
            by_model[model].append(record)
    for model, digest in expected_digests.items():
        records = sorted(by_model.get(model, []), key=lambda item: item.get("warmup_index", -1))
        if len(records) < 4:
            errors.append(f"model {model!r} has fewer than four auditable warm-up records")
            continue
        indices = [record.get("warmup_index") for record in records]
        if indices != list(range(1, len(records) + 1)):
            errors.append(f"model {model!r} warm-up order is inconsistent")
        candidates: list[int] = []
        for record in records:
            if record.get("valid") is not True or record.get("model_digest") != digest:
                errors.append(f"model {model!r} has an invalid warm-up record")
            cached = record.get("prompt_eval_cached_count")
            prompt_count = record.get("prompt_eval_count")
            if (
                not isinstance(cached, int)
                or isinstance(cached, bool)
                or not isinstance(prompt_count, int)
                or isinstance(prompt_count, bool)
                or cached < 0
                or cached > prompt_count
            ):
                errors.append(f"model {model!r} has unusable warm-up cache counters")
            elif record.get("warmup_index") != 1:
                candidates.append(cached)
            if record.get("warmup_index") != 1:
                load_duration = record.get("load_duration_ns")
                if (
                    not isinstance(load_duration, int)
                    or isinstance(load_duration, bool)
                    or load_duration < 0
                    or load_duration > 100_000_000
                ):
                    errors.append(
                        f"model {model!r} reloaded during cache-floor warm-up "
                        f"{record.get('warmup_index')!r}"
                    )
        if candidates and expected_floors.get(model) != min(candidates):
            errors.append(
                f"model {model!r} warm-up records do not support the declared cache floor"
            )


def _validate_measured_records(
    requests: tuple[dict[str, Any], ...],
    outputs: tuple[dict[str, Any], ...],
    telemetry: tuple[dict[str, Any], ...],
    expected_digests: dict[str, str],
    expected_floors: dict[str, int],
    errors: list[str],
) -> None:
    request_ids = [record.get("request_id") for record in requests]
    output_ids = [record.get("request_id") for record in outputs]
    if len(request_ids) != len(set(request_ids)):
        errors.append(f"{REQUESTS} contains duplicate request IDs")
    if set(request_ids) != set(output_ids):
        errors.append(f"{REQUESTS} and {OUTPUTS} do not describe the same request IDs")

    telemetry_times: dict[str, list[float]] = defaultdict(list)
    for record in telemetry:
        request_id = record.get("request_id")
        timestamp = record.get("monotonic_s")
        if isinstance(request_id, str) and isinstance(timestamp, int | float):
            telemetry_times[request_id].append(float(timestamp))

    for output in outputs:
        request_id = output.get("request_id")
        label = repr(request_id)
        if output.get("valid") is not True:
            errors.append(f"request {label} is invalid for primary analysis")
        model = output.get("model")
        digest = expected_digests.get(model)
        if digest is None or output.get("model_digest") != digest:
            errors.append(f"request {label} model digest does not match the manifest")
        required_runtime_metrics = {
            "latency_s": (int, float),
            "ttft_s": (int, float),
            "prompt_eval_count": (int,),
            "eval_count": (int,),
            "total_duration_ns": (int,),
            "prompt_eval_duration_ns": (int,),
            "eval_duration_ns": (int,),
        }
        for field, expected_types in required_runtime_metrics.items():
            value = output.get(field)
            valid_number = isinstance(value, expected_types) and not isinstance(value, bool)
            if not valid_number or value < 0 or (field != "ttft_s" and value == 0):
                errors.append(f"request {label} has no valid required runtime metric {field}")
        load_duration = output.get("load_duration_ns")
        if (
            not isinstance(load_duration, int)
            or isinstance(load_duration, bool)
            or load_duration < 0
            or load_duration > 100_000_000
        ):
            errors.append(f"request {label} reloaded the model or has no valid load duration")

        cached = output.get("prompt_eval_cached_count")
        prompt_count = output.get("prompt_eval_count")
        floor = expected_floors.get(model)
        cached_valid = isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0
        if not cached_valid:
            errors.append(f"request {label} has no valid cached prompt token count")
        elif (
            not isinstance(prompt_count, int)
            or isinstance(prompt_count, bool)
            or cached > prompt_count
        ):
            errors.append(f"request {label} cached prompt tokens exceed the prompt token count")
        elif floor is not None and cached > floor + 1:
            errors.append(f"request {label} used cached tokens above the allowed excess")

        metrics = output.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"request {label} has no derived metrics")
            continue
        energy = metrics.get("gpu_energy_joules")
        if not isinstance(energy, int | float) or isinstance(energy, bool) or energy <= 0:
            errors.append(f"request {label} has no positive GPU energy")
        if metrics.get("template_cache_baseline_tokens") != floor:
            errors.append(f"request {label} cache baseline does not match the manifest")
        expected_excess = max(0, cached - floor) if cached_valid and floor is not None else None
        if metrics.get("excess_cached_prompt_tokens") != expected_excess:
            errors.append(f"request {label} cached prompt excess is inconsistent")
        expected_uncached = (
            prompt_count - cached
            if isinstance(prompt_count, int) and cached_valid and prompt_count >= cached
            else None
        )
        if metrics.get("uncached_prompt_tokens") != expected_uncached:
            errors.append(f"request {label} uncached prompt token count is inconsistent")
        gap = metrics.get("max_telemetry_gap_seconds")
        if isinstance(gap, int | float) and not isinstance(gap, bool) and gap > 0.5:
            errors.append(f"request {label} has a telemetry gap above 500 ms")

        times = telemetry_times.get(request_id, [])
        if len(times) < 2:
            errors.append(f"request {label} has no telemetry coverage")
        elif any(right < left for left, right in zip(times, times[1:], strict=False)):
            errors.append(f"request {label} raw telemetry timestamp order is decreasing")
        elif any(right - left > 0.5 for left, right in zip(times, times[1:], strict=False)):
            errors.append(f"request {label} raw telemetry has a gap above 500 ms")
