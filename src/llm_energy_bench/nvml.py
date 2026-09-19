"""NVML capability probing and request-scoped GPU telemetry sampling.

Two rules shape this module.

First, consumer GPUs disagree about which NVML fields they expose. Nothing is
assumed to be supported: every field is probed, and an unsupported field is
reported as ``None``, never as a numeric zero that would silently pollute an
average.

Second, telemetry must survive failure. A sampling thread stops and flushes in
a ``finally`` block, a field that raises keeps the rest of the sample intact,
and samples taken before an interrupt are returned rather than discarded.
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import TracebackType
from typing import Any, Protocol

DEFAULT_INTERVAL_MS = 100
FINGERPRINT_LENGTH = 16
_THREAD_NAME = "nvml-sampler"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class NvmlError(Exception):
    """Base class for NVML problems this package understands."""


class NvmlUnavailable(NvmlError):
    """NVML, the driver, or the requested GPU is not present."""


class NvmlNotSupported(NvmlError):
    """The GPU or driver does not expose the requested field.

    This is an expected outcome on consumer hardware, not a failure. It is
    recorded as an absent capability rather than as a sampling error.
    """


class SamplerStateError(NvmlError):
    """The sampler was driven out of order (double start, sampling while closed)."""


# --------------------------------------------------------------------------
# Binding
# --------------------------------------------------------------------------


class NvmlBinding(Protocol):
    """The narrow slice of NVML this package needs.

    Keeping the surface small and raw-typed lets tests substitute a fake and
    reproduce every support matrix without an NVIDIA driver.
    """

    def initialize(self) -> None: ...
    def shutdown(self) -> None: ...
    def device_count(self) -> int: ...
    def device_handle(self, index: int) -> Any: ...
    def driver_version(self) -> str: ...
    def name(self, handle: Any) -> str: ...
    def uuid(self, handle: Any) -> str: ...
    def memory(self, handle: Any) -> tuple[int, int]: ...
    def total_energy_mj(self, handle: Any) -> int: ...
    def power_instant_mw(self, handle: Any) -> int: ...
    def power_legacy_mw(self, handle: Any) -> int: ...
    def temperature_c(self, handle: Any) -> int: ...
    def utilization(self, handle: Any) -> tuple[int, int]: ...
    def clocks_mhz(self, handle: Any) -> tuple[int, int]: ...
    def enforced_power_limit_mw(self, handle: Any) -> int: ...


class PynvmlBinding:
    """Adapter over ``nvidia-ml-py``.

    All NVML failures are translated here so that the rest of the package
    never sees a vendor exception type.
    """

    def __init__(self) -> None:
        self._nvml: Any = None

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        try:
            import pynvml
        except ImportError as error:  # pragma: no cover - depends on install
            raise NvmlUnavailable("nvidia-ml-py is not installed") from error

        try:
            pynvml.nvmlInit()
        except Exception as error:
            raise NvmlUnavailable(f"NVML could not be initialized: {error}") from error
        self._nvml = pynvml

    def shutdown(self) -> None:
        if self._nvml is None:
            return
        # Shutdown runs on the error path too; it must never mask the real failure.
        with contextlib.suppress(Exception):
            self._nvml.nvmlShutdown()
        self._nvml = None

    # -- helpers -----------------------------------------------------------

    @property
    def _api(self) -> Any:
        if self._nvml is None:
            raise NvmlUnavailable("NVML is not initialized")
        return self._nvml

    def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        try:
            return function(*args)
        except Exception as error:
            if self._is_not_supported(error):
                raise NvmlNotSupported(str(error)) from error
            raise

    def _is_not_supported(self, error: Exception) -> bool:
        not_supported = getattr(self._api, "NVML_ERROR_NOT_SUPPORTED", 3)
        if getattr(error, "value", None) == not_supported:
            return True
        return type(error).__name__ in {
            "NVMLError_NotSupported",
            "NVMLError_FunctionNotFound",
        }

    # -- device queries ----------------------------------------------------

    def device_count(self) -> int:
        return int(self._call(self._api.nvmlDeviceGetCount))

    def device_handle(self, index: int) -> Any:
        try:
            return self._api.nvmlDeviceGetHandleByIndex(index)
        except Exception as error:
            raise NvmlUnavailable(f"no NVIDIA GPU at index {index}: {error}") from error

    def driver_version(self) -> str:
        return _as_text(self._call(self._api.nvmlSystemGetDriverVersion))

    def name(self, handle: Any) -> str:
        return _as_text(self._call(self._api.nvmlDeviceGetName, handle))

    def uuid(self, handle: Any) -> str:
        return _as_text(self._call(self._api.nvmlDeviceGetUUID, handle))

    def memory(self, handle: Any) -> tuple[int, int]:
        info = self._call(self._api.nvmlDeviceGetMemoryInfo, handle)
        return int(info.total), int(info.used)

    def total_energy_mj(self, handle: Any) -> int:
        return int(self._call(self._api.nvmlDeviceGetTotalEnergyConsumption, handle))

    def power_instant_mw(self, handle: Any) -> int:
        """Read ``NVML_FI_DEV_POWER_INSTANT``, the unaveraged power draw."""
        api = self._api
        field_id = getattr(api, "NVML_FI_DEV_POWER_INSTANT", None)
        if field_id is None:
            raise NvmlNotSupported("NVML_FI_DEV_POWER_INSTANT is unknown to this binding")

        values = self._call(api.nvmlDeviceGetFieldValues, handle, [field_id])
        value = values[0]
        if value.nvmlReturn != getattr(api, "NVML_SUCCESS", 0):
            raise NvmlNotSupported(f"instant power field returned {value.nvmlReturn}")
        return int(value.value.uiVal)

    def power_legacy_mw(self, handle: Any) -> int:
        return int(self._call(self._api.nvmlDeviceGetPowerUsage, handle))

    def temperature_c(self, handle: Any) -> int:
        sensor = getattr(self._api, "NVML_TEMPERATURE_GPU", 0)
        return int(self._call(self._api.nvmlDeviceGetTemperature, handle, sensor))

    def utilization(self, handle: Any) -> tuple[int, int]:
        rates = self._call(self._api.nvmlDeviceGetUtilizationRates, handle)
        return int(rates.gpu), int(rates.memory)

    def clocks_mhz(self, handle: Any) -> tuple[int, int]:
        api = self._api
        sm = self._call(api.nvmlDeviceGetClockInfo, handle, getattr(api, "NVML_CLOCK_SM", 1))
        memory = self._call(api.nvmlDeviceGetClockInfo, handle, getattr(api, "NVML_CLOCK_MEM", 2))
        return int(sm), int(memory)

    def enforced_power_limit_mw(self, handle: Any) -> int:
        return int(self._call(self._api.nvmlDeviceGetEnforcedPowerLimit, handle))


def _as_text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


class EnergySource(StrEnum):
    """Where a run's energy figures come from, best source first."""

    TOTAL_ENERGY_COUNTER = "total_energy_counter"
    POWER_INSTANT_INTEGRATION = "power_instant_integration"
    POWER_LEGACY_INTEGRATION = "power_legacy_integration"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class GpuCapabilities:
    """What one GPU actually exposes, resolved by probing rather than assumed."""

    gpu_index: int
    name: str
    gpu_fingerprint: str
    driver_version: str
    vram_total_bytes: int | None
    supports_total_energy: bool
    supports_power_instant: bool
    supports_power_legacy: bool
    supports_temperature: bool
    supports_utilization: bool
    supports_clocks: bool
    supports_power_limit: bool
    power_limit_watts: float | None
    energy_source: EnergySource
    energy_fallback_reason: str | None
    unsupported_fields: tuple[str, ...] = ()
    field_errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_index": self.gpu_index,
            "name": self.name,
            "gpu_fingerprint": self.gpu_fingerprint,
            "driver_version": self.driver_version,
            "vram_total_bytes": self.vram_total_bytes,
            "supports_total_energy": self.supports_total_energy,
            "supports_power_instant": self.supports_power_instant,
            "supports_power_legacy": self.supports_power_legacy,
            "supports_temperature": self.supports_temperature,
            "supports_utilization": self.supports_utilization,
            "supports_clocks": self.supports_clocks,
            "supports_power_limit": self.supports_power_limit,
            "power_limit_watts": self.power_limit_watts,
            "energy_source": self.energy_source.value,
            "energy_fallback_reason": self.energy_fallback_reason,
            "unsupported_fields": list(self.unsupported_fields),
            "field_errors": dict(self.field_errors),
        }


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """One GPU observation inside a single request window.

    Every measured field is optional. ``None`` means "this GPU does not report
    it" or "this read failed"; the two cases are distinguished by ``errors``.
    """

    request_id: str
    monotonic_s: float
    utc: datetime
    power_instant_watts: float | None
    power_legacy_watts: float | None
    total_energy_joules: float | None
    temperature_c: int | None
    vram_total_bytes: int | None
    vram_used_bytes: int | None
    gpu_utilization_percent: int | None
    memory_utilization_percent: int | None
    sm_clock_mhz: int | None
    memory_clock_mhz: int | None
    power_limit_watts: float | None
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "monotonic_s": self.monotonic_s,
            "utc": self.utc.isoformat(),
            "power_instant_watts": self.power_instant_watts,
            "power_legacy_watts": self.power_legacy_watts,
            "total_energy_joules": self.total_energy_joules,
            "temperature_c": self.temperature_c,
            "vram_total_bytes": self.vram_total_bytes,
            "vram_used_bytes": self.vram_used_bytes,
            "gpu_utilization_percent": self.gpu_utilization_percent,
            "memory_utilization_percent": self.memory_utilization_percent,
            "sm_clock_mhz": self.sm_clock_mhz,
            "memory_clock_mhz": self.memory_clock_mhz,
            "power_limit_watts": self.power_limit_watts,
            "errors": dict(self.errors),
        }


# --------------------------------------------------------------------------
# Sampler
# --------------------------------------------------------------------------


class NvmlSampler:
    """Probes one GPU and samples it for the duration of a single request.

    Usage is ``open`` once per run, then ``start``/``stop`` per request::

        with NvmlSampler(gpu_index=0) as sampler:
            sampler.start(request_id)
            ...
            samples = sampler.stop()
    """

    def __init__(
        self,
        binding: NvmlBinding | None = None,
        gpu_index: int = 0,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError(f"interval_ms must be positive, got {interval_ms}")

        self._binding: NvmlBinding = binding if binding is not None else PynvmlBinding()
        self.gpu_index = gpu_index
        self.interval_ms = interval_ms

        self._handle: Any = None
        self._open = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[TelemetrySample] = []
        self._request_id: str | None = None
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        """Initialize NVML and resolve the device handle."""
        if self._open:
            return
        self._binding.initialize()
        try:
            self._check_index(self.gpu_index)
            self._handle = self._binding.device_handle(self.gpu_index)
        except Exception:
            self._binding.shutdown()
            raise
        self._open = True

    def close(self) -> None:
        """Stop any running sampler thread and shut NVML down.

        Safe to call twice, and safe to call while a request is in flight.
        """
        if not self._open:
            return
        try:
            self._halt_thread()
        finally:
            self._handle = None
            self._open = False
            self._binding.shutdown()

    def __enter__(self) -> NvmlSampler:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def is_sampling(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- probing -----------------------------------------------------------

    def probe(self, gpu_index: int | None = None) -> GpuCapabilities:
        """Report what this GPU exposes, opening NVML only if needed."""
        index = self.gpu_index if gpu_index is None else gpu_index
        opened_here = not self._open
        if opened_here:
            self._binding.initialize()

        try:
            self._check_index(index)
            handle = self._handle if (self._open and index == self.gpu_index) else None
            if handle is None:
                handle = self._binding.device_handle(index)
            return self._probe_device(index, handle)
        finally:
            if opened_here:
                self._binding.shutdown()

    def _check_index(self, index: int) -> None:
        count = self._binding.device_count()
        if index < 0 or index >= count:
            raise NvmlUnavailable(f"GPU index {index} is out of range; {count} GPU(s) visible")

    def _probe_device(self, index: int, handle: Any) -> GpuCapabilities:
        errors: dict[str, str] = {}

        supports = {
            name: self._read(name, reader, errors) is not None
            for name, reader in (
                ("memory", lambda: self._binding.memory(handle)),
                ("total_energy_mj", lambda: self._binding.total_energy_mj(handle)),
                ("power_instant_mw", lambda: self._binding.power_instant_mw(handle)),
                ("power_legacy_mw", lambda: self._binding.power_legacy_mw(handle)),
                ("temperature_c", lambda: self._binding.temperature_c(handle)),
                ("utilization", lambda: self._binding.utilization(handle)),
                ("clocks_mhz", lambda: self._binding.clocks_mhz(handle)),
                ("enforced_power_limit_mw", lambda: self._binding.enforced_power_limit_mw(handle)),
            )
        }

        # Re-read the two fields whose values the manifest needs, not just
        # their availability.
        memory = self._read("memory", lambda: self._binding.memory(handle), errors)
        power_limit_mw = self._read(
            "enforced_power_limit_mw",
            lambda: self._binding.enforced_power_limit_mw(handle),
            errors,
        )

        source, reason = _select_energy_source(
            total_energy=supports["total_energy_mj"],
            power_instant=supports["power_instant_mw"],
            power_legacy=supports["power_legacy_mw"],
        )

        return GpuCapabilities(
            gpu_index=index,
            name=self._binding.name(handle),
            gpu_fingerprint=fingerprint(self._binding.uuid(handle)),
            driver_version=self._binding.driver_version(),
            vram_total_bytes=memory[0] if memory else None,
            supports_total_energy=supports["total_energy_mj"],
            supports_power_instant=supports["power_instant_mw"],
            supports_power_legacy=supports["power_legacy_mw"],
            supports_temperature=supports["temperature_c"],
            supports_utilization=supports["utilization"],
            supports_clocks=supports["clocks_mhz"],
            supports_power_limit=supports["enforced_power_limit_mw"],
            power_limit_watts=_milli(power_limit_mw),
            energy_source=source,
            energy_fallback_reason=reason,
            unsupported_fields=tuple(
                name for name, ok in supports.items() if not ok and name not in errors
            ),
            field_errors=errors,
        )

    # -- sampling ----------------------------------------------------------

    def start(self, request_id: str) -> None:
        """Begin sampling for ``request_id``, taking one sample immediately."""
        if not self._open:
            raise SamplerStateError("the sampler is not open; call open() first")
        if self.is_sampling:
            raise SamplerStateError(
                f"already sampling {self._request_id!r}; stop() before starting {request_id!r}"
            )

        self._request_id = request_id
        self._samples = []
        self._stop_event = threading.Event()
        self._record(self._take_sample(request_id))

        self._thread = threading.Thread(
            target=self._loop,
            name=f"{_THREAD_NAME}-{request_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> tuple[TelemetrySample, ...]:
        """Stop sampling and return every sample taken, including partial ones."""
        if self._thread is None:
            return ()

        request_id = self._request_id
        try:
            self._halt_thread()
            if request_id is not None and self._open:
                self._record(self._take_sample(request_id))
        finally:
            self._request_id = None

        with self._lock:
            samples = tuple(self._samples)
            self._samples = []
        return samples

    def _halt_thread(self) -> None:
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self.interval_ms / 1000 * 5))

    def _loop(self) -> None:
        interval = self.interval_ms / 1000
        request_id = self._request_id or ""
        deadline = time.monotonic()
        try:
            while not self._stop_event.is_set():
                deadline += interval
                # A slow read must not make the sampler fall permanently behind.
                wait = max(0.0, deadline - time.monotonic())
                if self._stop_event.wait(wait):
                    break
                self._record(self._take_sample(request_id))
        finally:
            self._stop_event.set()

    def _record(self, sample: TelemetrySample) -> None:
        with self._lock:
            self._samples.append(sample)

    def _take_sample(self, request_id: str) -> TelemetrySample:
        handle = self._handle
        errors: dict[str, str] = {}
        read = {
            name: self._read(name, reader, errors)
            for name, reader in (
                ("total_energy_mj", lambda: self._binding.total_energy_mj(handle)),
                ("power_instant_mw", lambda: self._binding.power_instant_mw(handle)),
                ("power_legacy_mw", lambda: self._binding.power_legacy_mw(handle)),
                ("temperature_c", lambda: self._binding.temperature_c(handle)),
                ("memory", lambda: self._binding.memory(handle)),
                ("utilization", lambda: self._binding.utilization(handle)),
                ("clocks_mhz", lambda: self._binding.clocks_mhz(handle)),
                ("enforced_power_limit_mw", lambda: self._binding.enforced_power_limit_mw(handle)),
            )
        }
        memory = read["memory"]
        utilization = read["utilization"]
        clocks = read["clocks_mhz"]

        return TelemetrySample(
            request_id=request_id,
            monotonic_s=time.monotonic(),
            utc=datetime.now(UTC),
            power_instant_watts=_milli(read["power_instant_mw"]),
            power_legacy_watts=_milli(read["power_legacy_mw"]),
            total_energy_joules=_milli(read["total_energy_mj"]),
            temperature_c=read["temperature_c"],
            vram_total_bytes=memory[0] if memory else None,
            vram_used_bytes=memory[1] if memory else None,
            gpu_utilization_percent=utilization[0] if utilization else None,
            memory_utilization_percent=utilization[1] if utilization else None,
            sm_clock_mhz=clocks[0] if clocks else None,
            memory_clock_mhz=clocks[1] if clocks else None,
            power_limit_watts=_milli(read["enforced_power_limit_mw"]),
            errors=errors,
        )

    @staticmethod
    def _read(name: str, reader: Callable[[], Any], errors: dict[str, str]) -> Any:
        """Read one field, degrading to ``None`` instead of failing the sample.

        An unsupported field is a fact about the hardware and is not recorded
        as an error; anything else is, so that a flaky driver stays visible in
        the raw artifacts.
        """
        try:
            return reader()
        except NvmlNotSupported:
            return None
        except Exception as error:
            errors[name] = f"{type(error).__name__}: {error}"
            return None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def fingerprint(gpu_uuid: str) -> str:
    """Hash a GPU UUID so public artifacts identify a GPU without exposing it."""
    digest = hashlib.sha256(gpu_uuid.encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_LENGTH]


def _milli(value: int | None) -> float | None:
    """Convert a milli-unit NVML reading to its base unit, preserving ``None``."""
    return None if value is None else value / 1000.0


def _select_energy_source(
    *, total_energy: bool, power_instant: bool, power_legacy: bool
) -> tuple[EnergySource, str | None]:
    """Pick the best energy source and say why a better one was unavailable."""
    if total_energy:
        return EnergySource.TOTAL_ENERGY_COUNTER, None
    if power_instant:
        return (
            EnergySource.POWER_INSTANT_INTEGRATION,
            "the total-energy counter is unsupported; integrating instantaneous power",
        )
    if power_legacy:
        return (
            EnergySource.POWER_LEGACY_INTEGRATION,
            "neither the total-energy counter nor instantaneous power is supported; "
            "integrating averaged legacy power",
        )
    return (
        EnergySource.UNAVAILABLE,
        "this GPU reports no energy or power field; energy cannot be measured",
    )
