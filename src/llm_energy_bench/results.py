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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any

MAX_ARTIFACT_BYTES = 25 * 1024 * 1024

MANIFEST = "manifest.json"
RESOLVED_CONFIG = "config.resolved.toml"
REQUESTS = "requests.jsonl"
OUTPUTS = "outputs.jsonl"
TELEMETRY = "telemetry.jsonl.gz"
VALIDATION = "validation.json"
SUMMARY = "summary.csv"
REPORT = "report.md"

REQUIRED_RAW_ARTIFACTS = (MANIFEST, RESOLVED_CONFIG, REQUESTS, OUTPUTS, TELEMETRY)
DERIVED_ARTIFACTS = (VALIDATION, SUMMARY, REPORT)
RUN_ARTIFACTS = REQUIRED_RAW_ARTIFACTS + DERIVED_ARTIFACTS

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
    for name in (REQUESTS, OUTPUTS):
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


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------
#
# Two rules from the approved analysis methodology govern everything below.
#
# Ratios are aggregated, never averaged. A configuration's tokens per joule is
# total tokens over total joules, not the mean of per-request ratios, because
# the mean would let a tiny request count as much as a long one.
#
# Prompts are weighted equally. Repetitions are collapsed within a prompt
# first, and only then are prompts combined, so a prompt that happened to be
# measured more often does not dominate the configuration it describes.

QUALITY_FLOOR = 0.75


def aggregate_ratio(numerators: Sequence[float], denominators: Sequence[float]) -> float | None:
    """Total over total, which is the only ratio that survives being combined."""
    total_denominator = sum(d for d in denominators if d is not None)
    if not numerators or total_denominator <= 0:
        return None
    return sum(n for n in numerators if n is not None) / total_denominator


def weighted_over_prompts(per_prompt: Mapping[str, float]) -> float | None:
    """Combine per-prompt values with equal weight per prompt."""
    values = [v for v in per_prompt.values() if v is not None]
    return sum(values) / len(values) if values else None


def median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def iqr(values: Sequence[float]) -> float | None:
    """Interquartile range; zero for fewer than four points rather than undefined."""
    if not values:
        return None
    if len(values) < 4:
        return max(values) - min(values)
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return quartiles[2] - quartiles[0]


def coefficient_of_variation(values: Sequence[float]) -> float | None:
    """Repeatability of a measurement, used later to size a material inversion."""
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return statistics.stdev(values) / mean


@dataclass(frozen=True, slots=True)
class PromptAggregate:
    """One prompt under one model, with its repetitions collapsed."""

    model: str
    prompt_id: str
    prompt_category: str
    repetitions: int
    invalid: int
    latency_median_s: float | None
    latency_iqr_s: float | None
    latency_cv: float | None
    ttft_median_s: float | None
    output_tokens: int
    decode_tokens_per_s: float | None
    end_to_end_tokens_per_s: float | None
    energy_joules: float | None
    average_power_watts: float | None
    joules_per_output_token: float | None
    output_tokens_per_joule: float | None
    quality_pass_rate: float | None

    def to_row(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__slots__}


@dataclass(frozen=True, slots=True)
class ConfigurationSummary:
    """One run's worth of measurements, combined under the analysis rules."""

    run_id: str
    host_id: str
    model: str
    energy_source: str | None
    measured_requests: int
    invalid_requests: int
    prompts: tuple[PromptAggregate, ...]
    decode_tokens_per_s: float | None
    end_to_end_tokens_per_s: float | None
    output_tokens_per_joule: float | None
    joules_per_output_token: float | None
    cost_per_million_output_tokens: float | None
    currency: str | None
    quality_score: float | None
    repeatability_cv: float | None

    @property
    def eligible(self) -> bool:
        """Only a configuration that answers correctly enough may be ranked."""
        return self.quality_score is None or self.quality_score >= QUALITY_FLOOR

    @property
    def label(self) -> str:
        return f"{self.host_id} / {self.model}"


@dataclass(frozen=True, slots=True)
class ReportPaths:
    """What a report run produced."""

    summaries: tuple[Path, ...]
    reports: tuple[Path, ...]
    comparison_markdown: str


def _valid(records: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in records if r.get("valid")]


def _numbers(records: Iterable[Mapping[str, Any]], key: str) -> list[float]:
    return [r[key] for r in records if r.get(key) is not None]


def summarize_run(run_dir: Path) -> tuple[ConfigurationSummary, ...]:
    """Collapse one run directory into one summary per model."""
    report = validate_run(run_dir)
    if not report.checksums or MANIFEST not in report.checksums:
        raise ResultsError(f"{run_dir.name} is not a run directory: no {MANIFEST}")

    manifest = json.loads((run_dir / MANIFEST).read_text(encoding=_ENCODING))
    records = read_jsonl(run_dir / REQUESTS)
    config = manifest.get("config", {})

    summaries = []
    for model in config.get("models", []):
        model_records = [r for r in records if r.get("model") == model]
        if model_records:
            summaries.append(_summarize_model(manifest, model, model_records))
    return tuple(summaries)


def _summarize_model(
    manifest: Mapping[str, Any], model: str, records: Sequence[Mapping[str, Any]]
) -> ConfigurationSummary:
    config = manifest.get("config", {})
    by_prompt: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        by_prompt.setdefault(str(record.get("prompt_id", "")), []).append(record)

    prompts = tuple(
        _summarize_prompt(model, prompt_id, group) for prompt_id, group in sorted(by_prompt.items())
    )

    # Equal weight per prompt: collapse repetitions first, then combine prompts.
    decode = weighted_over_prompts(
        {p.prompt_id: p.decode_tokens_per_s for p in prompts if p.decode_tokens_per_s is not None}
    )
    end_to_end = weighted_over_prompts(
        {
            p.prompt_id: p.end_to_end_tokens_per_s
            for p in prompts
            if p.end_to_end_tokens_per_s is not None
        }
    )
    per_joule = weighted_over_prompts(
        {
            p.prompt_id: p.output_tokens_per_joule
            for p in prompts
            if p.output_tokens_per_joule is not None
        }
    )
    per_token = weighted_over_prompts(
        {
            p.prompt_id: p.joules_per_output_token
            for p in prompts
            if p.joules_per_output_token is not None
        }
    )
    scored = {p.prompt_id: p.quality_pass_rate for p in prompts if p.quality_pass_rate is not None}
    cvs = [p.latency_cv for p in prompts if p.latency_cv is not None]

    tariff = config.get("tariff_per_kwh")
    cost = None if per_token is None or tariff is None else per_token * 1e6 / 3_600_000.0 * tariff

    return ConfigurationSummary(
        run_id=str(manifest.get("run_id", "")),
        host_id=str(config.get("host_id", "")),
        model=model,
        energy_source=(manifest.get("gpu") or {}).get("energy_source"),
        measured_requests=len(records),
        invalid_requests=sum(1 for r in records if not r.get("valid")),
        prompts=prompts,
        decode_tokens_per_s=decode,
        end_to_end_tokens_per_s=end_to_end,
        output_tokens_per_joule=per_joule,
        joules_per_output_token=per_token,
        cost_per_million_output_tokens=cost,
        currency=config.get("currency") if tariff is not None else None,
        quality_score=weighted_over_prompts(scored),
        repeatability_cv=sum(cvs) / len(cvs) if cvs else None,
    )


def _summarize_prompt(
    model: str, prompt_id: str, group: Sequence[Mapping[str, Any]]
) -> PromptAggregate:
    valid = _valid(group)
    latencies = _numbers(valid, "latency_s")
    tokens = _numbers(valid, "output_tokens")
    energies = _numbers(valid, "energy_joules")
    eval_seconds = [r["eval_duration_ns"] / 1e9 for r in valid if r.get("eval_duration_ns")]
    judged = [r["quality_pass"] for r in group if r.get("quality_pass") is not None]

    return PromptAggregate(
        model=model,
        prompt_id=prompt_id,
        prompt_category=str(group[0].get("prompt_category", "")),
        repetitions=len(group),
        invalid=len(group) - len(valid),
        latency_median_s=median(latencies),
        latency_iqr_s=iqr(latencies),
        latency_cv=coefficient_of_variation(latencies),
        ttft_median_s=median(_numbers(valid, "ttft_s")),
        output_tokens=int(sum(tokens)),
        decode_tokens_per_s=aggregate_ratio(tokens, eval_seconds),
        end_to_end_tokens_per_s=aggregate_ratio(tokens, latencies),
        energy_joules=sum(energies) if energies else None,
        average_power_watts=(
            statistics.fmean(_numbers(valid, "average_power_watts"))
            if _numbers(valid, "average_power_watts")
            else None
        ),
        joules_per_output_token=aggregate_ratio(energies, tokens),
        output_tokens_per_joule=aggregate_ratio(tokens, energies),
        quality_pass_rate=sum(judged) / len(judged) if judged else None,
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def build_report(run_dirs: Sequence[Path]) -> ReportPaths:
    """Write summary.csv and report.md into each run, and compare across runs.

    Reports are derived: regenerating them never repeats inference and never
    changes the raw artifacts they are built from.
    """
    if not run_dirs:
        raise ResultsError("at least one run directory is required")

    summaries: list[Path] = []
    reports: list[Path] = []
    all_configs: list[ConfigurationSummary] = []

    for run_dir in run_dirs:
        configs = summarize_run(Path(run_dir))
        all_configs.extend(configs)
        summary_path = Path(run_dir) / SUMMARY
        report_path = Path(run_dir) / REPORT
        write_text(summary_path, _render_csv(configs))
        write_text(report_path, _render_markdown(Path(run_dir), configs))
        summaries.append(summary_path)
        reports.append(report_path)

    comparison = _render_comparison(all_configs) if len(all_configs) > 1 else ""
    return ReportPaths(tuple(summaries), tuple(reports), comparison)


_CSV_COLUMNS = (
    "run_id",
    "host_id",
    "model",
    "prompt_id",
    "prompt_category",
    "repetitions",
    "invalid",
    "latency_median_s",
    "latency_iqr_s",
    "latency_cv",
    "ttft_median_s",
    "output_tokens",
    "decode_tokens_per_s",
    "end_to_end_tokens_per_s",
    "energy_joules",
    "average_power_watts",
    "joules_per_output_token",
    "output_tokens_per_joule",
    "quality_pass_rate",
)


def _render_csv(configs: Sequence[ConfigurationSummary]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for config in configs:
        for prompt in config.prompts:
            row = prompt.to_row()
            row["run_id"] = config.run_id
            row["host_id"] = config.host_id
            writer.writerow({column: _csv_value(row.get(column)) for column in _CSV_COLUMNS})
    return buffer.getvalue()


def _csv_value(value: Any) -> Any:
    """Render a float at fixed precision so a regenerated report is byte-identical."""
    if isinstance(value, float):
        return f"{value:.6f}"
    return "" if value is None else value


def _render_markdown(run_dir: Path, configs: Sequence[ConfigurationSummary]) -> str:
    validation = validate_run(run_dir)
    lines = [
        f"# Run report: {run_dir.name}",
        "",
        f"Status: **{validation.status.value}**"
        + ("" if validation.ok else f" — {len(validation.errors)} validation error(s)"),
        "",
    ]
    for error in validation.errors:
        lines.append(f"- error: {error}")
    if validation.errors:
        lines.append("")

    for config in configs:
        lines += _render_configuration(config)

    lines += [
        "## Method notes",
        "",
        "- Ratios are aggregated as totals over totals, never as averages of",
        "  per-request ratios.",
        "- Repetitions are collapsed within each prompt before prompts are",
        "  combined, so every prompt carries equal weight.",
        "- A configuration enters the engineering ranking only at a quality",
        f"  score of at least {QUALITY_FLOOR:.0%}.",
        "- Any cost shown is a GPU-only electricity estimate. It excludes the",
        "  processor, system memory, power-supply losses, and cooling, and it is",
        "  not a total cost of ownership.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _render_configuration(config: ConfigurationSummary) -> list[str]:
    quality = (
        "not scored"
        if config.quality_score is None
        else f"{config.quality_score:.0%}"
        + ("" if config.eligible else f" — below {QUALITY_FLOOR:.0%}, excluded from ranking")
    )
    lines = [
        f"## {config.label}",
        "",
        f"- Measured requests: {config.measured_requests} ({config.invalid_requests} invalid)",
        f"- Energy source: `{config.energy_source}`",
        f"- Quality: {quality}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Decode throughput | {_number(config.decode_tokens_per_s, 'tok/s')} |",
        f"| End-to-end throughput | {_number(config.end_to_end_tokens_per_s, 'tok/s')} |",
        f"| Energy per output token | {_number(config.joules_per_output_token, 'J/tok')} |",
        f"| Output tokens per joule | {_number(config.output_tokens_per_joule, 'tok/J')} |",
        f"| Cost per 1M output tokens | {_cost_cell(config)} |",
        f"| Repeatability (latency CV) | {_number(config.repeatability_cv, '')} |",
        "",
        "| Prompt | Category | Reps | Latency median (s) | IQR | tok/s | J/tok | Quality |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for prompt in config.prompts:
        lines.append(
            f"| {prompt.prompt_id} | {prompt.prompt_category} | {prompt.repetitions} "
            f"| {_number(prompt.latency_median_s, '')} | {_number(prompt.latency_iqr_s, '')} "
            f"| {_number(prompt.decode_tokens_per_s, '')} "
            f"| {_number(prompt.joules_per_output_token, '')} "
            f"| {'—' if prompt.quality_pass_rate is None else f'{prompt.quality_pass_rate:.0%}'} |"
        )
    lines.append("")
    return lines


def _number(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    rendered = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{rendered} {unit}".strip()


def _cost_cell(config: ConfigurationSummary) -> str:
    if config.cost_per_million_output_tokens is None:
        return "— (no tariff configured)"
    return (
        f"{config.cost_per_million_output_tokens:.4f} {config.currency} "
        "(GPU-only electricity estimate)"
    )


def _render_comparison(configs: Sequence[ConfigurationSummary]) -> str:
    """Rank the configurations by speed and by energy, and say whether they agree."""
    eligible = [c for c in configs if c.eligible]
    lines = [
        "# Cross-run comparison",
        "",
        "| Configuration | Decode tok/s | tok/J | Quality | Ranked |",
        "| --- | --- | --- | --- | --- |",
    ]
    for config in configs:
        lines.append(
            f"| {config.label} | {_number(config.decode_tokens_per_s, '')} "
            f"| {_number(config.output_tokens_per_joule, '')} "
            f"| {'—' if config.quality_score is None else f'{config.quality_score:.0%}'} "
            f"| {'yes' if config.eligible else 'no'} |"
        )
    lines.append("")

    if not eligible:
        lines += [
            f"No configuration reached the {QUALITY_FLOOR:.0%} quality floor, so none is",
            "ranked. The measurements stand; the engineering comparison does not.",
            "",
        ]
        return "\n".join(lines) + "\n"

    fastest = _best(eligible, "decode_tokens_per_s")
    most_efficient = _best(eligible, "output_tokens_per_joule")
    lines += [
        f"- Fastest (speed-only): **{fastest.label}**" if fastest else "- Fastest: —",
        f"- Most efficient (energy-aware): **{most_efficient.label}**"
        if most_efficient
        else "- Most efficient: —",
        "",
    ]
    if fastest and most_efficient:
        if fastest.label == most_efficient.label:
            lines += [
                "Speed and energy select the same configuration here. On its own this",
                "supports no conclusion: the hypothesis is judged over workload blocks,",
                "not over a single comparison.",
                "",
            ]
        else:
            lines += [
                "Speed and energy select **different** configurations. Whether this is a",
                "material rank inversion depends on the effect size and repeatability,",
                "which this report does not yet decide.",
                "",
            ]
    return "\n".join(lines) + "\n"


def _best(configs: Sequence[ConfigurationSummary], field: str) -> ConfigurationSummary | None:
    ranked = [c for c in configs if getattr(c, field) is not None]
    return max(ranked, key=lambda c: getattr(c, field)) if ranked else None


# --------------------------------------------------------------------------
# Environment diagnosis
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Whether this host can produce a measurement worth trusting."""

    ok: bool
    ollama_version: str | None
    gpu: dict[str, Any]
    installed_models: tuple[str, ...]
    loaded_models: tuple[dict[str, Any], ...]
    problems: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ollama_version": self.ollama_version,
            "gpu": dict(self.gpu),
            "installed_models": list(self.installed_models),
            "loaded_models": [dict(m) for m in self.loaded_models],
            "problems": list(self.problems),
            "notes": list(self.notes),
        }

    def render(self) -> str:
        lines = [f"Ollama: {self.ollama_version or 'unavailable'}"]
        gpu_name = self.gpu.get("name")
        lines.append(f"GPU: {gpu_name or 'unavailable'}")
        if self.gpu.get("energy_source"):
            lines.append(f"Energy source: {self.gpu['energy_source']}")
        lines.append(f"Installed models: {len(self.installed_models)}")
        for model in self.installed_models:
            lines.append(f"  - {model}")
        for loaded in self.loaded_models:
            fraction = loaded.get("gpu_fraction")
            placement = "unknown" if fraction is None else f"{fraction:.1%} in VRAM"
            lines.append(f"  loaded: {loaded.get('name')} ({placement})")
        for note in self.notes:
            lines.append(f"note: {note}")
        for problem in self.problems:
            lines.append(f"PROBLEM: {problem}")
        lines.append("OK" if self.ok else "NOT READY")
        return "\n".join(lines)


def diagnose(*, client: Any, sampler: Any, config: Any = None) -> DoctorReport:
    """Inspect the host without measuring anything.

    Every check degrades into a reported problem. A doctor that raises cannot
    tell the user what else is wrong.
    """
    problems: list[str] = []
    notes: list[str] = []

    version: str | None = None
    installed: tuple[str, ...] = ()
    loaded: tuple[dict[str, Any], ...] = ()
    try:
        version = client.version()
        installed = tuple(model.name for model in client.list_models())
        loaded = tuple(model.to_dict() for model in client.running_models())
    except Exception as error:
        problems.append(f"Ollama is not usable: {error}")

    gpu: dict[str, Any] = {}
    try:
        sampler.open()
        try:
            caps = sampler.probe()
            gpu = caps.to_dict()
        finally:
            sampler.close()
    except Exception as error:
        problems.append(f"GPU telemetry via NVML is unavailable: {error}")

    if gpu:
        source = gpu.get("energy_source")
        if source == "unavailable":
            problems.append(
                f"{gpu.get('name')} exposes no energy or power field, "
                "so energy cannot be measured on this host"
            )
        elif source != "total_energy_counter":
            notes.append(
                "the total-energy counter is unsupported; energy will be integrated "
                f"from power ({source})"
            )
        for field_name in gpu.get("unsupported_fields", []):
            notes.append(f"NVML does not support {field_name} on this GPU")
        for field_name, message in (gpu.get("field_errors") or {}).items():
            problems.append(f"NVML failed to read {field_name}: {message}")

    for model in loaded:
        fraction = model.get("gpu_fraction")
        if fraction is None:
            notes.append(f"{model.get('name')}: Ollama did not report where it is loaded")
        elif fraction < 0.999:
            problems.append(
                f"{model.get('name')} is only {fraction:.1%} resident in VRAM; "
                "partial CPU offload invalidates a primary GPU run"
            )

    if config is not None and version is not None:
        for model in getattr(config, "models", ()):
            if model not in installed:
                problems.append(
                    f"{model} is not installed on this host; pull it manually, "
                    "since the bench never downloads a model"
                )

    return DoctorReport(
        ok=not problems,
        ollama_version=version,
        gpu=gpu,
        installed_models=installed,
        loaded_models=loaded,
        problems=tuple(problems),
        notes=tuple(notes),
    )
