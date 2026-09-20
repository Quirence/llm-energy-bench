"""Fakes for the Ollama client and the NVML sampler.

The runner coordinates two pieces of hardware-dependent machinery. These fakes
let every ordering, failure, and telemetry-support combination be reproduced
without a GPU or an inference server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from llm_energy_bench.nvml import EnergySource, GpuCapabilities, TelemetrySample
from llm_energy_bench.ollama import (
    AvailableModel,
    InferenceRequest,
    InferenceResult,
    InvalidKind,
    ModelNotFound,
    RunningModel,
)

DIGEST = "sha256:0123456789abcdef"


def capabilities(
    energy_source: EnergySource = EnergySource.TOTAL_ENERGY_COUNTER,
) -> GpuCapabilities:
    return GpuCapabilities(
        gpu_index=0,
        name="NVIDIA GeForce RTX 3050 Laptop GPU",
        gpu_fingerprint="54a50433af3c357a",
        driver_version="560.94",
        vram_total_bytes=4 * 1024**3,
        supports_total_energy=energy_source is EnergySource.TOTAL_ENERGY_COUNTER,
        supports_power_instant=energy_source is not EnergySource.POWER_LEGACY_INTEGRATION,
        supports_power_legacy=True,
        supports_temperature=True,
        supports_utilization=True,
        supports_clocks=True,
        supports_power_limit=True,
        power_limit_watts=60.0,
        energy_source=energy_source,
        energy_fallback_reason=None if energy_source is EnergySource.TOTAL_ENERGY_COUNTER else "x",
    )


def sample(
    request_id: str,
    monotonic_s: float,
    *,
    power: float | None = 45.0,
    energy_j: float | None = None,
    temperature: int | None = 60,
    vram_used: int | None = 2 * 1024**3,
) -> TelemetrySample:
    return TelemetrySample(
        request_id=request_id,
        monotonic_s=monotonic_s,
        utc=datetime.now(UTC),
        power_instant_watts=power,
        power_legacy_watts=None if power is None else power - 0.5,
        total_energy_joules=energy_j,
        temperature_c=temperature,
        vram_total_bytes=4 * 1024**3,
        vram_used_bytes=vram_used,
        gpu_utilization_percent=97,
        memory_utilization_percent=41,
        sm_clock_mhz=1875,
        memory_clock_mhz=6000,
        power_limit_watts=60.0,
        errors={},
    )


@dataclass
class FakeSampler:
    """Records its own lifecycle so the runner's cleanup can be asserted."""

    caps: GpuCapabilities = field(default_factory=capabilities)
    samples_per_request: int = 3
    power: float | None = 45.0
    energy_step_j: float = 4.5
    opened: int = 0
    closed: int = 0
    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    is_sampling: bool = False
    _current: str | None = None
    _energy: float = 1000.0
    _clock: float = 0.0

    def probe(self, gpu_index: int | None = None) -> GpuCapabilities:
        return self.caps

    def open(self) -> None:
        self.opened += 1

    def close(self) -> None:
        self.closed += 1
        self.is_sampling = False

    def __enter__(self) -> FakeSampler:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self, request_id: str) -> None:
        self.started.append(request_id)
        self._current = request_id
        self.is_sampling = True

    def stop(self) -> tuple[TelemetrySample, ...]:
        if self._current is None:
            return ()
        request_id, self._current = self._current, None
        self.stopped.append(request_id)
        self.is_sampling = False

        collected = []
        uses_counter = self.caps.energy_source is EnergySource.TOTAL_ENERGY_COUNTER
        for _ in range(self.samples_per_request):
            self._clock += 1.0
            if uses_counter:
                self._energy += self.energy_step_j
            collected.append(
                sample(
                    request_id,
                    self._clock,
                    power=self.power,
                    energy_j=self._energy if uses_counter else None,
                )
            )
        return tuple(collected)


@dataclass
class FakeOllamaClient:
    """Answers preflight questions and returns scripted generations."""

    installed: tuple[str, ...] = ("llama3.2:3b-instruct-q4_K_M",)
    size_bytes: int = 2_000_000_000
    size_vram_bytes: int | None = None
    eval_count: int | None = 120
    prompt_eval_count: int | None = 300
    fail_on: dict[str, InvalidKind] = field(default_factory=dict)
    raise_on_request: dict[str, BaseException] = field(default_factory=dict)
    prompts_seen: list[str] = field(default_factory=list)
    requests_seen: list[InferenceRequest] = field(default_factory=list)
    preloaded: list[str] = field(default_factory=list)
    closed: int = 0

    def __post_init__(self) -> None:
        if self.size_vram_bytes is None:
            self.size_vram_bytes = self.size_bytes

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self.closed += 1

    def __enter__(self) -> FakeOllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- inventory ---------------------------------------------------------

    def version(self) -> str:
        return "0.3.14"

    def list_models(self) -> tuple[AvailableModel, ...]:
        return tuple(
            AvailableModel(
                name=name,
                model=name,
                digest=DIGEST,
                size_bytes=self.size_bytes,
                format="gguf",
                family="llama",
                parameter_size="3.2B",
                quantization="Q4_K_M",
            )
            for name in self.installed
        )

    def running_models(self) -> tuple[RunningModel, ...]:
        return tuple(self._running(name) for name in self.preloaded)

    def _running(self, name: str) -> RunningModel:
        return RunningModel(
            name=name,
            model=name,
            digest=DIGEST,
            size_bytes=self.size_bytes,
            size_vram_bytes=self.size_vram_bytes,
            quantization="Q4_K_M",
            parameter_size="3.2B",
            family="llama",
            context_length=4096,
        )

    def preload(self, model: str) -> RunningModel:
        if model not in self.installed:
            raise ModelNotFound(f"model {model!r} is not installed")
        if model not in self.preloaded:
            self.preloaded.append(model)
        return self._running(model)

    # -- generation --------------------------------------------------------

    def generate_stream(self, request: InferenceRequest) -> InferenceResult:
        self.prompts_seen.append(request.prompt)
        self.requests_seen.append(request)

        if request.request_id in self.raise_on_request:
            raise self.raise_on_request[request.request_id]

        kind = self.fail_on.get(request.request_id)
        now = datetime.now(UTC)
        return InferenceResult(
            request_id=request.request_id,
            model=request.model,
            model_digest=DIGEST,
            started_utc=now,
            ended_utc=now,
            t_start_s=0.0,
            t_first_chunk_s=None if kind else 0.2,
            t_first_token_s=None if kind else 0.2,
            t_end_s=2.0,
            ttft_s=None if kind else 0.2,
            latency_s=2.0,
            text="" if kind else "generated text",
            chunk_count=0 if kind else 12,
            done=kind is None,
            done_reason=None if kind else "stop",
            http_status=200,
            prompt_eval_count=None if kind else self.prompt_eval_count,
            eval_count=None if kind else self.eval_count,
            total_duration_ns=None if kind else 2_000_000_000,
            load_duration_ns=None if kind else 50_000_000,
            prompt_eval_duration_ns=None if kind else 400_000_000,
            eval_duration_ns=None if kind else 1_500_000_000,
            valid=kind is None,
            invalid_kind=kind,
            invalid_reason=None if kind is None else f"scripted failure: {kind.value}",
        )
