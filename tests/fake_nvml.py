"""A fake NVML binding.

Real NVML cannot be exercised in CI, and consumer GPUs disagree about which
fields they support. The fake lets every support combination and every failure
mode be reproduced deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llm_energy_bench.nvml import NvmlNotSupported, NvmlUnavailable

FULL_SUPPORT = (
    "total_energy_mj",
    "power_instant_mw",
    "power_legacy_mw",
    "temperature_c",
    "utilization",
    "clocks_mhz",
    "enforced_power_limit_mw",
    "memory",
)


@dataclass
class FakeNvml:
    """Configurable stand-in for :mod:`pynvml`."""

    supported: tuple[str, ...] = FULL_SUPPORT
    raises: dict[str, Exception] = field(default_factory=dict)
    device_count_value: int = 1
    driver: str = "560.94"
    device_name: str = "NVIDIA GeForce RTX 3050 Laptop GPU"
    device_uuid: str = "GPU-12345678-90ab-cdef-1234-567890abcdef"
    vram_total: int = 4 * 1024**3
    vram_used: int = 1 * 1024**3
    power_mw: int = 45_000
    energy_mj: int = 1_000_000
    init_calls: int = 0
    shutdown_calls: int = 0
    available: bool = True
    calls: list[str] = field(default_factory=list)

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        if not self.available:
            raise NvmlUnavailable("NVML library not found")
        self.init_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    # -- helpers -----------------------------------------------------------

    def _field(self, name: str) -> None:
        self.calls.append(name)
        if name in self.raises:
            raise self.raises[name]
        if name not in self.supported:
            raise NvmlNotSupported(name)

    # -- device queries ----------------------------------------------------

    def device_count(self) -> int:
        return self.device_count_value

    def device_handle(self, index: int) -> Any:
        if index >= self.device_count_value:
            raise NvmlUnavailable(f"no GPU at index {index}")
        return f"handle-{index}"

    def name(self, handle: Any) -> str:
        return self.device_name

    def uuid(self, handle: Any) -> str:
        return self.device_uuid

    def driver_version(self) -> str:
        return self.driver

    def memory(self, handle: Any) -> tuple[int, int]:
        self._field("memory")
        return self.vram_total, self.vram_used

    def total_energy_mj(self, handle: Any) -> int:
        self._field("total_energy_mj")
        self.energy_mj += 4_500
        return self.energy_mj

    def power_instant_mw(self, handle: Any) -> int:
        self._field("power_instant_mw")
        return self.power_mw

    def power_legacy_mw(self, handle: Any) -> int:
        self._field("power_legacy_mw")
        return self.power_mw - 500

    def temperature_c(self, handle: Any) -> int:
        self._field("temperature_c")
        return 63

    def utilization(self, handle: Any) -> tuple[int, int]:
        self._field("utilization")
        return 97, 41

    def clocks_mhz(self, handle: Any) -> tuple[int, int]:
        self._field("clocks_mhz")
        return 1875, 6000

    def enforced_power_limit_mw(self, handle: Any) -> int:
        self._field("enforced_power_limit_mw")
        return 60_000
