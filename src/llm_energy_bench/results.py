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

import getpass
import gzip
import hashlib
import json
import os
import re
import secrets
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
