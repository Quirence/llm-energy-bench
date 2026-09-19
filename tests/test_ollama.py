"""Tests for the Ollama client: model inventory, placement, and streaming measurements.

Every test runs against ``FakeOllama``, an in-process stand-in served through
``httpx.MockTransport``. No real Ollama server is needed, and the fake refuses
any endpoint that would download or mutate a model.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
import pytest

from llm_energy_bench import ollama
from llm_energy_bench.ollama import (
    InferenceRequest,
    InvalidKind,
    ModelNotFound,
    OllamaClient,
    OllamaProtocolError,
    OllamaUnavailable,
)

MODEL = "llama3.2:3b-instruct-q4_K_M"
DIGEST = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
OTHER_MODEL = "qwen3:4b-instruct-2507-q8_0"
OTHER_DIGEST = "e9f0c2a1b3d4c5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e"
MODEL_SIZE = 3_400_000_000
BASE_URL = "http://ollama.test:11434"

_ABSENT = object()  # marks a field the fake server omits entirely

MUTATING_ENDPOINTS = (
    "/api/pull",
    "/api/push",
    "/api/create",
    "/api/copy",
    "/api/delete",
)


# --------------------------------------------------------------------------
# Fake Ollama
# --------------------------------------------------------------------------


def tag_entry(name: str = MODEL, digest: str = DIGEST, quant: str = "Q4_K_M") -> dict[str, Any]:
    return {
        "name": name,
        "model": name,
        "modified_at": "2026-09-01T10:00:00+03:00",
        "size": 2_019_393_189,
        "digest": digest,
        "details": {
            "format": "gguf",
            "family": "llama",
            "families": ["llama"],
            "parameter_size": "3.2B",
            "quantization_level": quant,
        },
    }


def ps_entry(
    name: str = MODEL,
    digest: str = DIGEST,
    size: int | None = MODEL_SIZE,
    size_vram: int | None = MODEL_SIZE,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "model": name,
        "digest": digest,
        "details": {
            "format": "gguf",
            "family": "llama",
            "quantization_level": "Q4_K_M",
        },
        "expires_at": "2026-09-19T12:05:00+03:00",
        "context_length": 4096,
    }
    if size is not None:
        entry["size"] = size
    if size_vram is not None:
        entry["size_vram"] = size_vram
    return entry


def token(text: str) -> dict[str, Any]:
    return {
        "model": MODEL,
        "created_at": "2026-09-19T12:00:00Z",
        "response": text,
        "done": False,
    }


def final(**overrides: Any) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "model": MODEL,
        "created_at": "2026-09-19T12:00:01Z",
        "response": "",
        "done": True,
        "done_reason": "stop",
        "context": [128006, 882, 128007],
        "total_duration": 1_234_567_891,
        "load_duration": 12_345_678,
        "prompt_eval_count": 26,
        "prompt_eval_duration": 45_678_912,
        "eval_count": 3,
        "eval_duration": 987_654_321,
    }
    chunk.update(overrides)
    return {key: value for key, value in chunk.items() if value is not _ABSENT}


def ndjson(*chunks: dict[str, Any]) -> list[bytes]:
    # Ollama sends raw UTF-8, not \u escapes.
    return [json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n" for chunk in chunks]


class ChunkStream(httpx.SyncByteStream):
    """A response body delivered piece by piece, optionally failing midway."""

    def __init__(
        self, pieces: list[bytes], error: Exception | None = None, delay_s: float = 0.0
    ) -> None:
        self._pieces = pieces
        self._error = error
        self._delay_s = delay_s

    def __iter__(self) -> Iterator[bytes]:
        for piece in self._pieces:
            if self._delay_s:
                time.sleep(self._delay_s)
            yield piece
        if self._error is not None:
            raise self._error


@dataclass
class FakeOllama:
    """Configurable stand-in for an Ollama server."""

    models: list[dict[str, Any]] = field(default_factory=lambda: [tag_entry()])
    running: list[dict[str, Any]] = field(default_factory=list)
    stream_pieces: list[bytes] = field(
        default_factory=lambda: ndjson(token("Hello"), token(","), token(" world"), final())
    )
    stream_error: Exception | None = None
    stream_delay_s: float = 0.0
    generate_status: int = 200
    generate_error: str = "internal error"
    vram_share: float = 1.0
    unavailable: bool = False
    tags_body: Any = None
    requests: list[tuple[str, str, dict[str, Any] | None]] = field(default_factory=list)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def client(self, **kwargs: Any) -> OllamaClient:
        return OllamaClient(BASE_URL, transport=self.transport, **kwargs)

    @property
    def paths(self) -> list[str]:
        return [path for _, path, _ in self.requests]

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, body))

        if path in MUTATING_ENDPOINTS:
            raise AssertionError(f"the client must never call {path}")
        if self.unavailable:
            raise httpx.ConnectError("[WinError 10061] connection refused", request=request)

        if (request.method, path) == ("GET", "/api/version"):
            return httpx.Response(200, json={"version": "0.12.3"})
        if (request.method, path) == ("GET", "/api/tags"):
            payload = {"models": self.models} if self.tags_body is None else self.tags_body
            return httpx.Response(200, json=payload)
        if (request.method, path) == ("GET", "/api/ps"):
            return httpx.Response(200, json={"models": self.running})
        if (request.method, path) == ("POST", "/api/generate"):
            assert body is not None
            if "prompt" not in body:
                return self._load(body["model"])
            return self._generate()
        raise AssertionError(f"unexpected request {request.method} {path}")

    def _load(self, model: str) -> httpx.Response:
        entry = next((m for m in self.models if m["name"] == model), None)
        if entry is None:
            return httpx.Response(404, json={"error": f"model '{model}' not found"})
        self.running = [
            ps_entry(model, entry["digest"], MODEL_SIZE, int(MODEL_SIZE * self.vram_share))
        ]
        return httpx.Response(
            200,
            json={"model": model, "response": "", "done": True, "done_reason": "load"},
        )

    def _generate(self) -> httpx.Response:
        if self.generate_status != 200:
            return httpx.Response(self.generate_status, json={"error": self.generate_error})
        return httpx.Response(
            200,
            headers={"content-type": "application/x-ndjson"},
            stream=ChunkStream(self.stream_pieces, self.stream_error, self.stream_delay_s),
        )


def request(**overrides: Any) -> InferenceRequest:
    fields: dict[str, Any] = {
        "request_id": "req-0001",
        "model": MODEL,
        "prompt": "[req-0001] Say hello.",
        "options": {"num_ctx": 4096, "temperature": 0, "seed": 42},
    }
    fields.update(overrides)
    return InferenceRequest(**fields)


def preloaded(fake: FakeOllama, **kwargs: Any) -> OllamaClient:
    client = fake.client(**kwargs)
    client.preload(MODEL)
    return client


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------


def test_a_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="timeout"):
        OllamaClient(BASE_URL, timeout_s=0)


def test_a_non_http_base_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="http"):
        OllamaClient("ollama.test:11434")


def test_the_client_is_a_context_manager() -> None:
    with FakeOllama().client() as client:
        assert client.list_models()


def test_the_runtime_version_is_reported() -> None:
    assert FakeOllama().client().version() == "0.12.3"


# --------------------------------------------------------------------------
# Inventory and placement
# --------------------------------------------------------------------------


def test_list_models_reports_digest_and_quantization() -> None:
    fake = FakeOllama(models=[tag_entry(), tag_entry(OTHER_MODEL, OTHER_DIGEST, "Q8_0")])
    models = fake.client().list_models()

    assert [m.name for m in models] == [MODEL, OTHER_MODEL]
    assert models[0].digest == DIGEST
    assert models[0].quantization == "Q4_K_M"
    assert models[0].parameter_size == "3.2B"
    assert models[1].digest == OTHER_DIGEST
    assert models[1].quantization == "Q8_0"


def test_running_models_report_full_gpu_placement() -> None:
    fake = FakeOllama(running=[ps_entry()])
    (model,) = fake.client().running_models()

    assert model.name == MODEL
    assert model.digest == DIGEST
    assert model.size_bytes == MODEL_SIZE
    assert model.size_vram_bytes == MODEL_SIZE
    assert model.gpu_fraction == pytest.approx(1.0)
    assert model.fully_on_gpu is True
    assert model.quantization == "Q4_K_M"
    assert model.context_length == 4096


def test_partial_cpu_offload_is_reported_as_a_fact_not_rejected() -> None:
    """Rejecting offloaded runs is preflight policy (Task 6), not the client's."""
    fake = FakeOllama(running=[ps_entry(size_vram=MODEL_SIZE // 4)])
    (model,) = fake.client().running_models()

    assert model.gpu_fraction == pytest.approx(0.25)
    assert model.fully_on_gpu is False


@pytest.mark.parametrize(
    ("size", "size_vram"),
    [(0, 0), (None, MODEL_SIZE), (MODEL_SIZE, None)],
)
def test_unknown_placement_is_null_without_dividing_by_zero(
    size: int | None, size_vram: int | None
) -> None:
    fake = FakeOllama(running=[ps_entry(size=size, size_vram=size_vram)])
    (model,) = fake.client().running_models()

    assert model.gpu_fraction is None
    assert model.fully_on_gpu is None


def test_a_malformed_inventory_is_a_protocol_error() -> None:
    fake = FakeOllama(tags_body={"models": "not-a-list"})
    with pytest.raises(OllamaProtocolError):
        fake.client().list_models()


@pytest.mark.parametrize(
    "call",
    [
        lambda client: client.list_models(),
        lambda client: client.running_models(),
        lambda client: client.preload(MODEL),
        lambda client: client.version(),
    ],
    ids=["list_models", "running_models", "preload", "version"],
)
def test_an_unreachable_server_raises_unavailable(call: Any) -> None:
    with pytest.raises(OllamaUnavailable):
        call(FakeOllama(unavailable=True).client())


# --------------------------------------------------------------------------
# Preload
# --------------------------------------------------------------------------


def test_preload_loads_the_model_and_returns_its_placement() -> None:
    fake = FakeOllama()
    running = fake.client().preload(MODEL)

    assert running.name == MODEL
    assert running.digest == DIGEST
    assert running.fully_on_gpu is True

    load = [body for method, path, body in fake.requests if path == "/api/generate"]
    assert load == [{"model": MODEL, "stream": False}]  # no prompt: load only


def test_preload_reports_offload_without_rejecting_it() -> None:
    running = FakeOllama(vram_share=0.5).client().preload(MODEL)

    assert running.gpu_fraction == pytest.approx(0.5)
    assert running.fully_on_gpu is False


def test_preload_rejects_a_missing_model_without_pulling_it() -> None:
    fake = FakeOllama(models=[tag_entry(OTHER_MODEL, OTHER_DIGEST)])

    with pytest.raises(ModelNotFound, match=MODEL):
        fake.client().preload(MODEL)

    assert "/api/pull" not in fake.paths
    assert "/api/generate" not in fake.paths  # never even asked to load it


def test_a_bare_model_name_resolves_to_the_latest_tag() -> None:
    fake = FakeOllama(models=[tag_entry("llama3.2:latest")])
    running = fake.client().preload("llama3.2")

    assert running.name == "llama3.2:latest"
    assert running.digest == DIGEST


# --------------------------------------------------------------------------
# Normal generation
# --------------------------------------------------------------------------


def test_generation_sends_one_deterministic_streaming_request() -> None:
    fake = FakeOllama()
    preloaded(fake).generate_stream(request(keep_alive="30m"))

    method, path, body = fake.requests[-1]
    assert (method, path) == ("POST", "/api/generate")
    assert body == {
        "model": MODEL,
        "prompt": "[req-0001] Say hello.",
        "stream": True,
        "options": {"num_ctx": 4096, "temperature": 0, "seed": 42},
        "keep_alive": "30m",
    }


def test_normal_generation_records_text_counts_and_raw_durations() -> None:
    result = preloaded(FakeOllama()).generate_stream(request())

    assert result.valid is True
    assert result.invalid_kind is None
    assert result.invalid_reason is None
    assert result.request_id == "req-0001"
    assert result.model == MODEL
    assert result.text == "Hello, world"
    assert result.chunk_count == 4
    assert result.done is True
    assert result.done_reason == "stop"
    assert result.http_status == 200

    assert result.prompt_eval_count == 26
    assert result.eval_count == 3
    # Raw nanoseconds, exactly as Ollama sent them: no conversion, no rounding.
    assert result.total_duration_ns == 1_234_567_891
    assert result.load_duration_ns == 12_345_678
    assert result.prompt_eval_duration_ns == 45_678_912
    assert result.eval_duration_ns == 987_654_321
    assert all(
        isinstance(value, int)
        for value in (
            result.total_duration_ns,
            result.load_duration_ns,
            result.prompt_eval_duration_ns,
            result.eval_duration_ns,
        )
    )


def test_client_timestamps_are_ordered_and_latency_is_end_to_end() -> None:
    fake = FakeOllama(stream_delay_s=0.01)
    result = preloaded(fake).generate_stream(request())

    assert result.t_start_s <= result.t_first_chunk_s <= result.t_first_token_s <= result.t_end_s
    assert result.latency_s == pytest.approx(result.t_end_s - result.t_start_s)
    assert result.ttft_s == pytest.approx(result.t_first_token_s - result.t_start_s)
    assert result.latency_s >= 0.04  # four pieces, 10 ms apart
    assert result.started_utc.tzinfo is not None
    assert result.started_utc <= result.ended_utc


def test_ttft_waits_for_the_first_non_empty_text() -> None:
    fake = FakeOllama(
        stream_pieces=ndjson(token(""), token(""), token("Hi"), final(eval_count=1)),
        stream_delay_s=0.02,
    )
    result = preloaded(fake).generate_stream(request())

    assert result.valid is True
    # Two empty chunks arrive first; TTFT must not stop the clock on them.
    assert result.t_first_token_s - result.t_first_chunk_s >= 0.03
    assert result.ttft_s is not None
    assert result.ttft_s >= 0.05


def test_multibyte_text_split_across_network_reads_is_preserved() -> None:
    body = b"".join(ndjson(token("Привет, мир"), final(eval_count=2)))
    split = body.index("мир".encode()) + 1  # cut inside a two-byte character
    fake = FakeOllama(stream_pieces=[body[:split], body[split:]])

    result = preloaded(fake).generate_stream(request())

    assert result.valid is True
    assert result.text == "Привет, мир"


def test_the_result_serializes_to_plain_json() -> None:
    result = preloaded(FakeOllama()).generate_stream(request())
    record = json.loads(json.dumps(result.to_dict()))

    assert record["text"] == "Hello, world"
    assert record["model_digest"] == DIGEST
    assert record["total_duration_ns"] == 1_234_567_891
    assert record["invalid_kind"] is None
    datetime.fromisoformat(record["started_utc"])
    assert "context" not in record  # the token context is bulky and not a measurement


def test_inventory_records_serialize_to_plain_json() -> None:
    fake = FakeOllama(running=[ps_entry(size_vram=None)])
    client = fake.client()

    tags = json.loads(json.dumps([m.to_dict() for m in client.list_models()]))
    ps = json.loads(json.dumps([m.to_dict() for m in client.running_models()]))

    assert tags[0]["digest"] == DIGEST
    assert ps[0]["size_vram_bytes"] is None
    assert ps[0]["gpu_fraction"] is None


# --------------------------------------------------------------------------
# Digest capture
# --------------------------------------------------------------------------


def test_the_digest_comes_from_the_preloaded_model() -> None:
    result = preloaded(FakeOllama()).generate_stream(request())
    assert result.model_digest == DIGEST


def test_the_digest_is_resolved_from_the_host_without_a_preload() -> None:
    fake = FakeOllama()
    result = fake.client().generate_stream(request())

    assert result.model_digest == DIGEST
    # Resolution happens before the clock starts, not inside the request window.
    assert fake.paths == ["/api/tags", "/api/generate"]


def test_the_digest_distinguishes_models_sharing_a_client() -> None:
    fake = FakeOllama(models=[tag_entry(), tag_entry(OTHER_MODEL, OTHER_DIGEST, "Q8_0")])
    client = fake.client()

    assert client.generate_stream(request()).model_digest == DIGEST
    assert client.generate_stream(request(model=OTHER_MODEL)).model_digest == OTHER_DIGEST


def test_an_unresolvable_digest_is_null_not_the_tag() -> None:
    fake = FakeOllama(models=[])
    result = fake.client().generate_stream(request())

    assert result.model_digest is None


# --------------------------------------------------------------------------
# Boundary behaviour: every failure yields an auditable result
# --------------------------------------------------------------------------


def test_a_missing_final_chunk_preserves_the_partial_output() -> None:
    fake = FakeOllama(stream_pieces=ndjson(token("Hello"), token(", wor")))
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.MISSING_FINAL_CHUNK
    assert "final" in (result.invalid_reason or "")
    assert result.text == "Hello, wor"
    assert result.chunk_count == 2
    assert result.done is False
    assert result.done_reason is None
    assert result.ttft_s is not None
    assert result.latency_s is not None
    # Nothing the server never sent is invented.
    assert result.eval_count is None
    assert result.total_duration_ns is None


def test_a_timeout_mid_stream_returns_a_partial_invalid_result() -> None:
    fake = FakeOllama(
        stream_pieces=ndjson(token("Hello"), token(",")),
        stream_error=httpx.ReadTimeout("timed out"),
    )
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.TIMEOUT
    assert result.text == "Hello,"
    assert result.chunk_count == 2
    assert result.done is False
    assert result.t_end_s >= result.t_first_token_s
    assert result.latency_s is not None


def test_a_disconnect_mid_stream_returns_a_partial_invalid_result() -> None:
    fake = FakeOllama(
        stream_pieces=ndjson(token("Hello")),
        stream_error=httpx.RemoteProtocolError("peer closed connection without response"),
    )
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.DISCONNECTED
    assert result.text == "Hello"
    assert result.chunk_count == 1


def test_a_refused_connection_during_generation_is_recorded_not_raised() -> None:
    fake = FakeOllama()
    client = preloaded(fake)
    fake.unavailable = True

    result = client.generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.CONNECT_FAILED
    assert result.http_status is None
    assert result.chunk_count == 0
    assert result.text == ""
    assert result.ttft_s is None
    assert result.t_first_chunk_s is None
    assert result.latency_s is not None


@pytest.mark.parametrize(
    "final_chunk",
    [final(eval_count=0), final(eval_count=_ABSENT, eval_duration=_ABSENT)],
    ids=["eval_count_zero", "eval_count_absent"],
)
def test_zero_output_is_invalid_and_never_divides(final_chunk: dict[str, Any]) -> None:
    fake = FakeOllama(stream_pieces=ndjson(final_chunk))
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.NO_OUTPUT
    assert result.done is True
    assert result.text == ""
    assert result.ttft_s is None
    json.dumps(result.to_dict())  # still a complete, serializable record


def test_output_tokens_without_visible_text_are_invalid() -> None:
    fake = FakeOllama(stream_pieces=ndjson(token(""), final(eval_count=5)))
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.NO_OUTPUT
    assert result.eval_count == 5  # the raw count is kept even when invalid
    assert result.ttft_s is None


def test_an_error_line_inside_the_stream_is_invalid() -> None:
    fake = FakeOllama(
        stream_pieces=ndjson(token("Hel"))
        + [json.dumps({"error": "llama runner process has terminated"}).encode() + b"\n"],
    )
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.SERVER_ERROR
    assert "llama runner process has terminated" in (result.invalid_reason or "")
    assert result.text == "Hel"


def test_a_malformed_chunk_is_invalid() -> None:
    fake = FakeOllama(stream_pieces=ndjson(token("Hi")) + [b"{not json\n"])
    result = preloaded(fake).generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.MALFORMED_CHUNK
    assert result.text == "Hi"


def test_an_http_error_status_is_invalid_and_carries_the_server_message() -> None:
    fake = FakeOllama(generate_status=404, generate_error=f"model '{MODEL}' not found")
    result = fake.client().generate_stream(request())

    assert result.valid is False
    assert result.invalid_kind is InvalidKind.HTTP_ERROR
    assert result.http_status == 404
    assert "not found" in (result.invalid_reason or "")


def test_the_prompt_cache_fields_are_raw_and_absent_means_null() -> None:
    """Cached-prompt semantics are unverified on a live server; keep the raw fields."""
    fake = FakeOllama(
        stream_pieces=ndjson(
            token("Hi"), final(prompt_eval_count=_ABSENT, prompt_eval_duration=_ABSENT)
        )
    )
    result = preloaded(fake).generate_stream(request())

    assert result.valid is True
    assert result.prompt_eval_count is None  # absent is null, never zero
    assert result.prompt_eval_cached_count is None
    assert result.prompt_eval_duration_ns is None


def test_the_prompt_cache_count_is_preserved_from_the_final_chunk() -> None:
    fake = FakeOllama(
        stream_pieces=ndjson(token("Hi"), final(prompt_eval_cached_count=17))
    )

    result = preloaded(fake).generate_stream(request())

    assert result.prompt_eval_count == 26
    assert result.prompt_eval_cached_count == 17


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leak",
    [
        r"C:\Users\alice\.ollama\models\blobs\sha256-a80c4f17",
        "/home/alice/.ollama/models/blobs/sha256-a80c4f17",
        "/Users/alice/.ollama/models/blobs/sha256-a80c4f17",
    ],
)
def test_error_messages_never_carry_home_directories(leak: str) -> None:
    fake = FakeOllama(generate_status=500, generate_error=f"error loading model {leak}")
    result = fake.client().generate_stream(request())
    record = json.dumps(result.to_dict())

    assert "alice" not in record
    assert "sha256-a80c4f17" in (result.invalid_reason or "")  # the useful part survives


def test_unavailable_errors_never_carry_home_directories() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(r"cannot open C:\Users\alice\AppData\ollama.sock")

    client = OllamaClient(BASE_URL, transport=httpx.MockTransport(refuse))
    with pytest.raises(OllamaUnavailable) as caught:
        client.list_models()

    assert "alice" not in str(caught.value)


# --------------------------------------------------------------------------
# The client never downloads or mutates a model
# --------------------------------------------------------------------------


def test_a_full_scenario_never_downloads_or_mutates_a_model() -> None:
    fake = FakeOllama(models=[tag_entry(), tag_entry(OTHER_MODEL, OTHER_DIGEST, "Q8_0")])
    client = fake.client()

    client.version()
    client.list_models()
    client.running_models()
    client.preload(MODEL)
    client.generate_stream(request())
    client.generate_stream(request(model=OTHER_MODEL))
    with pytest.raises(ModelNotFound):
        client.preload("mistral:7b")
    fake.generate_status = 404
    client.generate_stream(request(model="mistral:7b"))

    assert fake.requests, "the scenario must have talked to the fake server"
    assert not set(fake.paths) & set(MUTATING_ENDPOINTS)
    assert set(fake.paths) <= {"/api/version", "/api/tags", "/api/ps", "/api/generate"}


def test_the_client_has_no_route_to_a_mutating_endpoint() -> None:
    assert not set(ollama.ALLOWED_ENDPOINTS) & set(MUTATING_ENDPOINTS)
