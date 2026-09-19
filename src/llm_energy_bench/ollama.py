"""Ollama model inventory, placement inspection, and streaming measurements.

Three rules shape this module.

First, the client never changes what is installed. It reads the inventory,
loads an already-present model into memory, and generates; it has no route to
``/api/pull`` or any other endpoint that downloads or mutates a model. A
missing model is an explicit error, because a run that fetched its own weights
would not be reproducible.

Second, a measurement always produces a record. Once a generation request is
sent, a timeout, a dropped connection, a missing final chunk, or an empty
answer yields an ``InferenceResult`` marked invalid, with every chunk and
timestamp gathered so far. Only a server that is unreachable as a whole raises
``OllamaUnavailable``, and only from the inventory and preload calls.

Third, the client reports facts, not conclusions. Ollama's counters and
nanosecond durations are stored exactly as received, absent values are
``None``, and no rate is derived here. Whether partial CPU offload or a prompt
cache hit disqualifies a request is decided by the runner.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import StrEnum
from types import TracebackType
from typing import Any

import httpx

DEFAULT_TIMEOUT_S = 300.0
CONNECT_TIMEOUT_S = 10.0
MAX_ERROR_LENGTH = 500

# The complete set of endpoints this client may call. Nothing here downloads,
# creates, copies, pushes, or deletes a model.
ALLOWED_ENDPOINTS = frozenset({"/api/version", "/api/tags", "/api/ps", "/api/generate"})


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class OllamaError(Exception):
    """Base class for Ollama problems this package understands."""


class OllamaUnavailable(OllamaError):
    """The Ollama server cannot be reached at all."""


class ModelNotFound(OllamaError):
    """The requested model is not installed on this host.

    The client never pulls it: models are downloaded by hand so that every run
    uses weights someone deliberately chose.
    """


class OllamaServerError(OllamaError):
    """Ollama answered an inventory or load call with an error status."""


class OllamaProtocolError(OllamaError):
    """Ollama answered, but not in the shape this client understands."""


class InvalidKind(StrEnum):
    """Why a generation produced no usable measurement."""

    CONNECT_FAILED = "connect_failed"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"
    HTTP_ERROR = "http_error"
    SERVER_ERROR = "server_error"
    MALFORMED_CHUNK = "malformed_chunk"
    MISSING_FINAL_CHUNK = "missing_final_chunk"
    NO_OUTPUT = "no_output"


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AvailableModel:
    """A model installed on the host, as listed by ``/api/tags``."""

    name: str
    model: str | None
    digest: str | None
    size_bytes: int | None
    format: str | None
    family: str | None
    parameter_size: str | None
    quantization: str | None

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_dict(self)


@dataclass(frozen=True, slots=True)
class RunningModel:
    """A model loaded in memory, as listed by ``/api/ps``.

    ``size_vram_bytes`` below ``size_bytes`` means part of the model runs on
    the CPU. The client only reports it; rejecting such a run is preflight
    policy.
    """

    name: str
    model: str | None
    digest: str | None
    size_bytes: int | None
    size_vram_bytes: int | None
    quantization: str | None
    parameter_size: str | None
    family: str | None
    context_length: int | None

    @property
    def gpu_fraction(self) -> float | None:
        """Share of the loaded model held in VRAM, or ``None`` when unknown."""
        if self.size_bytes is None or self.size_vram_bytes is None or self.size_bytes <= 0:
            return None
        return self.size_vram_bytes / self.size_bytes

    @property
    def fully_on_gpu(self) -> bool | None:
        """Whether the whole model is in VRAM, or ``None`` when unknown."""
        if self.gpu_fraction is None:
            return None
        return self.size_vram_bytes >= self.size_bytes  # type: ignore[operator]

    def to_dict(self) -> dict[str, Any]:
        record = _to_plain_dict(self)
        record["gpu_fraction"] = self.gpu_fraction
        record["fully_on_gpu"] = self.fully_on_gpu
        return record


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    """One measured prompt, sent exactly as given.

    The prompt is not rewritten here: cache-busting prefixes are the runner's
    responsibility. ``keep_alive`` is sent only when set.
    """

    request_id: str
    model: str
    prompt: str
    options: Mapping[str, Any] = field(default_factory=dict)
    keep_alive: str | int | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must not be empty")
        if not self.model:
            raise ValueError("model must not be empty")

    def to_dict(self) -> dict[str, Any]:
        record = _to_plain_dict(self)
        record["options"] = dict(self.options)
        return record


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """Everything observed while streaming one generation.

    Client timestamps (``t_*_s``) come from ``time.perf_counter``, a monotonic
    clock with sub-microsecond resolution on Windows and Linux; they are
    comparable only within one process. ``t_first_chunk_s`` marks the first
    chunk of any kind, ``t_first_token_s`` the first chunk carrying non-empty
    text, and TTFT is measured to the latter.

    Ollama's counters and ``*_duration_ns`` fields are copied verbatim from the
    final chunk and are ``None`` when that chunk is missing or omits them.
    """

    request_id: str
    model: str
    model_digest: str | None
    started_utc: datetime
    ended_utc: datetime
    t_start_s: float
    t_first_chunk_s: float | None
    t_first_token_s: float | None
    t_end_s: float
    ttft_s: float | None
    latency_s: float
    text: str
    chunk_count: int
    done: bool
    done_reason: str | None
    http_status: int | None
    prompt_eval_count: int | None
    prompt_eval_cached_count: int | None
    eval_count: int | None
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_eval_duration_ns: int | None
    eval_duration_ns: int | None
    valid: bool
    invalid_kind: InvalidKind | None
    invalid_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_dict(self)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class OllamaClient:
    """Talks to one Ollama server over its HTTP API.

    ``timeout_s`` bounds every network wait: connecting (capped at
    ``CONNECT_TIMEOUT_S`` so a dead server fails fast), sending, and the silence
    between two streamed chunks. It is not a limit on total generation time;
    output length is bounded by the request options.

    Environment proxy settings are ignored: a proxy between the client and a
    local server would add latency that is not the model's.
    """

    def __init__(
        self,
        base_url: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"base_url must start with http:// or https://, got {base_url!r}")
        if not (math.isfinite(timeout_s) and timeout_s > 0):
            raise ValueError(f"timeout_s must be positive and finite, got {timeout_s}")

        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, CONNECT_TIMEOUT_S)),
            transport=transport,
            trust_env=False,
        )
        self._digests: dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- inventory ---------------------------------------------------------

    def version(self) -> str:
        """Return the Ollama server version for the run manifest."""
        body = self._get_json("/api/version")
        version = body.get("version")
        if not isinstance(version, str):
            raise OllamaProtocolError("/api/version did not report a version string")
        return version

    def list_models(self) -> tuple[AvailableModel, ...]:
        """List installed models (``GET /api/tags``)."""
        models = tuple(
            AvailableModel(
                name=name,
                model=_optional_str(entry, "model"),
                digest=_optional_str(entry, "digest"),
                size_bytes=_optional_int(entry, "size"),
                format=_optional_str(details, "format"),
                family=_optional_str(details, "family"),
                parameter_size=_optional_str(details, "parameter_size"),
                quantization=_optional_str(details, "quantization_level"),
            )
            for name, entry, details in self._model_entries("/api/tags")
        )
        self._remember_digests(models)
        return models

    def running_models(self) -> tuple[RunningModel, ...]:
        """List models currently loaded in memory (``GET /api/ps``)."""
        models = tuple(
            RunningModel(
                name=name,
                model=_optional_str(entry, "model"),
                digest=_optional_str(entry, "digest"),
                size_bytes=_optional_int(entry, "size"),
                size_vram_bytes=_optional_int(entry, "size_vram"),
                quantization=_optional_str(details, "quantization_level"),
                parameter_size=_optional_str(details, "parameter_size"),
                family=_optional_str(details, "family"),
                context_length=_optional_int(entry, "context_length"),
            )
            for name, entry, details in self._model_entries("/api/ps")
        )
        self._remember_digests(models)
        return models

    def preload(self, model: str) -> RunningModel:
        """Load an installed model into memory and report where it landed.

        Raises ``ModelNotFound`` when the model is not installed; it is never
        downloaded.
        """
        available = _find(self.list_models(), model)
        if available is None:
            raise ModelNotFound(
                f"model {model!r} is not installed on this Ollama host; "
                f"pull it manually (ollama pull {model}) and record why"
            )

        response = self._send(
            "POST", "/api/generate", json={"model": available.name, "stream": False}
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            raise ModelNotFound(f"Ollama could not load {model!r}: {_error_message(response)}")
        if response.status_code != httpx.codes.OK:
            raise OllamaServerError(
                f"loading {model!r} failed with HTTP {response.status_code}: "
                f"{_error_message(response)}"
            )

        running = _find(self.running_models(), available.name)
        if running is None:
            raise OllamaProtocolError(f"{model!r} was loaded but /api/ps does not list it")
        return running

    # -- generation --------------------------------------------------------

    def generate_stream(self, request: InferenceRequest) -> InferenceResult:
        """Stream one generation and measure it from the client side.

        Never raises for network or server failures once the request is
        attempted: the result is returned with ``valid=False`` instead. The
        model digest is resolved before the clock starts, so an inventory
        lookup never falls inside the measured window.
        """
        digest = self._resolve_digest(request.model)
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": True,
            "options": dict(request.options),
        }
        if request.keep_alive is not None:
            payload["keep_alive"] = request.keep_alive

        stream = _Stream()
        started_utc = datetime.now(UTC)
        stream.t_start = time.perf_counter()
        try:
            with self._http.stream("POST", _endpoint("/api/generate"), json=payload) as response:
                stream.http_status = response.status_code
                if response.status_code == httpx.codes.OK:
                    stream.consume(response)
                else:
                    response.read()
                    stream.fail(
                        InvalidKind.HTTP_ERROR,
                        f"HTTP {response.status_code}: {_error_message(response)}",
                    )
        except httpx.HTTPError as error:
            stream.fail(_classify(error), f"{stream.progress()}: {_describe(error)}")
        if stream.t_end is None:
            stream.t_end = time.perf_counter()
        ended_utc = datetime.now(UTC)

        return stream.result(request, digest, started_utc, ended_utc)

    # -- internals ---------------------------------------------------------

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http.request(method, _endpoint(path), **kwargs)
        except httpx.HTTPError as error:
            raise OllamaUnavailable(
                f"Ollama at {_redact(self.base_url)} is unreachable: {_describe(error)}"
            ) from error

    def _get_json(self, path: str) -> dict[str, Any]:
        response = self._send("GET", path)
        if response.status_code != httpx.codes.OK:
            raise OllamaServerError(
                f"GET {path} failed with HTTP {response.status_code}: {_error_message(response)}"
            )
        try:
            body = response.json()
        except ValueError as error:
            raise OllamaProtocolError(f"GET {path} did not return JSON") from error
        if not isinstance(body, dict):
            raise OllamaProtocolError(f"GET {path} returned {type(body).__name__}, not an object")
        return body

    def _model_entries(self, path: str) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        models = self._get_json(path).get("models")
        if not isinstance(models, list):
            raise OllamaProtocolError(f"GET {path} did not return a model list")

        entries = []
        for entry in models:
            if not isinstance(entry, dict):
                raise OllamaProtocolError(f"GET {path} listed a non-object model entry")
            name = _optional_str(entry, "name") or _optional_str(entry, "model")
            if name is None:
                raise OllamaProtocolError(f"GET {path} listed a model without a name")
            details = entry.get("details")
            entries.append((name, entry, details if isinstance(details, dict) else {}))
        return entries

    def _remember_digests(self, models: tuple[AvailableModel | RunningModel, ...]) -> None:
        for model in models:
            if model.digest is not None:
                for name in (model.name, model.model):
                    if name:
                        self._digests[canonical_name(name)] = model.digest

    def _resolve_digest(self, model: str) -> str | None:
        key = canonical_name(model)
        if key not in self._digests:
            try:
                self.list_models()
            except OllamaError:
                # The generation itself will record why the server misbehaved.
                return None
        return self._digests.get(key)


# --------------------------------------------------------------------------
# Streaming state
# --------------------------------------------------------------------------


class _Stream:
    """Mutable accumulator for one generation; frozen into a result at the end."""

    def __init__(self) -> None:
        self.t_start = 0.0
        self.t_first_chunk: float | None = None
        self.t_first_token: float | None = None
        self.t_end: float | None = None
        self.http_status: int | None = None
        self.parts: list[str] = []
        self.chunk_count = 0
        self.final: dict[str, Any] | None = None
        self.invalid_kind: InvalidKind | None = None
        self.invalid_reason: str | None = None

    def fail(self, kind: InvalidKind, reason: str) -> None:
        # The first failure is the cause; later ones are consequences.
        if self.invalid_kind is None:
            self.invalid_kind = kind
            self.invalid_reason = _redact(reason)[:MAX_ERROR_LENGTH]

    def progress(self) -> str:
        if self.http_status is None:
            return "no response"
        return f"after {self.chunk_count} chunk(s)"

    def consume(self, response: httpx.Response) -> None:
        for line in response.iter_lines():
            if not line.strip():
                continue
            now = time.perf_counter()
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                self.fail(
                    InvalidKind.MALFORMED_CHUNK,
                    f"{self.progress()}: a chunk is not JSON",
                )
                return
            if not isinstance(chunk, dict):
                self.fail(
                    InvalidKind.MALFORMED_CHUNK,
                    f"{self.progress()}: a chunk is not an object",
                )
                return
            if "error" in chunk:
                self.fail(
                    InvalidKind.SERVER_ERROR,
                    f"{self.progress()}: Ollama reported an error: {chunk['error']}",
                )
                return

            text = chunk.get("response", "")
            if not isinstance(text, str):
                self.fail(
                    InvalidKind.MALFORMED_CHUNK,
                    f"{self.progress()}: 'response' is not text",
                )
                return

            self.chunk_count += 1
            if self.t_first_chunk is None:
                self.t_first_chunk = now
            if text:
                if self.t_first_token is None:
                    self.t_first_token = now
                self.parts.append(text)
            if chunk.get("done") is True:
                self.final = chunk
                self.t_end = now
                return

        self.fail(
            InvalidKind.MISSING_FINAL_CHUNK,
            f"the stream ended {self.progress()} without a final done chunk",
        )

    def result(
        self,
        request: InferenceRequest,
        digest: str | None,
        started_utc: datetime,
        ended_utc: datetime,
    ) -> InferenceResult:
        final = self.final or {}
        text = "".join(self.parts)
        eval_count = _optional_int(final, "eval_count")

        if self.final is not None and not eval_count:
            self.fail(
                InvalidKind.NO_OUTPUT,
                f"Ollama reported no output tokens (eval_count={eval_count})",
            )
        elif self.final is not None and not text:
            self.fail(
                InvalidKind.NO_OUTPUT,
                f"eval_count={eval_count} but no text was streamed",
            )

        t_end = self.t_end if self.t_end is not None else self.t_start
        return InferenceResult(
            request_id=request.request_id,
            model=request.model,
            model_digest=digest,
            started_utc=started_utc,
            ended_utc=ended_utc,
            t_start_s=self.t_start,
            t_first_chunk_s=self.t_first_chunk,
            t_first_token_s=self.t_first_token,
            t_end_s=t_end,
            ttft_s=None if self.t_first_token is None else self.t_first_token - self.t_start,
            latency_s=t_end - self.t_start,
            text=text,
            chunk_count=self.chunk_count,
            done=self.final is not None,
            done_reason=_optional_str(final, "done_reason"),
            http_status=self.http_status,
            prompt_eval_count=_optional_int(final, "prompt_eval_count"),
            prompt_eval_cached_count=_optional_int(final, "prompt_eval_cached_count"),
            eval_count=eval_count,
            total_duration_ns=_optional_int(final, "total_duration"),
            load_duration_ns=_optional_int(final, "load_duration"),
            prompt_eval_duration_ns=_optional_int(final, "prompt_eval_duration"),
            eval_duration_ns=_optional_int(final, "eval_duration"),
            valid=self.invalid_kind is None,
            invalid_kind=self.invalid_kind,
            invalid_reason=self.invalid_reason,
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def canonical_name(name: str) -> str:
    """Spell a model reference the way Ollama resolves it (``x`` is ``x:latest``)."""
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def _find[M: (AvailableModel, RunningModel)](models: tuple[M, ...], name: str) -> M | None:
    wanted = canonical_name(name)
    for model in models:
        if wanted in {
            canonical_name(model.name),
            canonical_name(model.model or model.name),
        }:
            return model
    return None


def _endpoint(path: str) -> str:
    if path not in ALLOWED_ENDPOINTS:
        raise ValueError(f"{path} is not an endpoint this client may call")
    return path


def _classify(error: httpx.HTTPError) -> InvalidKind:
    if isinstance(error, httpx.ConnectError | httpx.ConnectTimeout):
        return InvalidKind.CONNECT_FAILED
    if isinstance(error, httpx.TimeoutException):
        return InvalidKind.TIMEOUT
    if isinstance(error, httpx.DecodingError):
        return InvalidKind.MALFORMED_CHUNK
    return InvalidKind.DISCONNECTED


def _describe(error: BaseException) -> str:
    detail = _redact(str(error)).strip()
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    message = body.get("error") if isinstance(body, dict) else None
    if not isinstance(message, str):
        message = response.text or "no error message"
    return _redact(message)[:MAX_ERROR_LENGTH]


_REDACTIONS = (
    # Windows profile directories: C:\Users\name, D:/Users/name.
    (
        re.compile(r"\b[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\\/\s'\"]+", re.I),
        "<home>",
    ),
    # POSIX home directories: /home/name, /Users/name, /root.
    (re.compile(r"/(?:home|Users)/[^/\s'\"]+"), "<home>"),
    (re.compile(r"/root(?=[/\s'\"]|$)"), "<home>"),
    # Credentials embedded in URLs and bearer tokens.
    (re.compile(r"(?<=://)[^/\s@]+@"), "<redacted>@"),
    (re.compile(r"(?i)\b(bearer)\s+[\w.~+/=-]+"), r"\1 <redacted>"),
)


def _redact(text: str) -> str:
    """Strip home directories, user names in paths, and tokens from a message."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _optional_int(mapping: Mapping[str, Any], key: str) -> int | None:
    value = mapping.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) and value else None


def _to_plain_dict(record: Any) -> dict[str, Any]:
    """Serialize a record into values ``json.dumps`` accepts without help."""
    plain: dict[str, Any] = {}
    for item in fields(record):
        value = getattr(record, item.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, StrEnum):
            value = value.value
        plain[item.name] = value
    return plain
