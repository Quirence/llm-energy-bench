"""Experiment configuration and prompt-set contracts.

Everything here is validated eagerly and explicitly. A measurement campaign is
expensive and hard to repeat, so a wrong control must stop the run before any
inference happens rather than surface as an unexplained number afterwards.

Two rules follow from that:

* unknown keys are an error, not something to ignore. A silently dropped
  ``num_ctx`` would produce a run that is wrong in a way no artifact records;
* every resolved config and prompt set has a content fingerprint, so a run can
  be tied to the exact controls that produced it.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_WARMUP_REQUESTS = 4
DEFAULT_REPETITIONS = 3
DEFAULT_ORDER_SEED = 42
DEFAULT_TELEMETRY_INTERVAL_MS = 100
DEFAULT_NUM_CTX = 4096
DEFAULT_NUM_GPU = 999
DEFAULT_TEMPERATURE = 0.0
DEFAULT_INFERENCE_SEED = 42
DEFAULT_KV_CACHE = "f16"
DEFAULT_CONCURRENCY = 1

SUPPORTED_KV_CACHE = ("f16", "q8_0", "q4_0")

# Identifiers reach file names, manifests, and published reports, so they are
# restricted to characters that are safe everywhere and reveal nothing.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class ConfigError(Exception):
    """A configuration or prompt set that cannot be trusted to produce a valid run."""


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


class PromptCategory(StrEnum):
    """What a prompt is meant to stress.

    ``short`` favours decode, ``long`` favours prefill, and ``scored`` carries
    a checkable expectation so a configuration can be held to the quality floor.
    """

    SHORT = "short"
    LONG = "long"
    SCORED = "scored"


class HostRole(StrEnum):
    """How a host contributes to the power-quality-v2 study."""

    PRIMARY = "primary"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class PromptCase:
    """One prompt, identified by a stable ID that survives into every artifact."""

    prompt_id: str
    category: PromptCategory
    prompt: str
    expect_contains: tuple[str, ...] = ()
    expect_exact: str | None = None

    @property
    def is_scored(self) -> bool:
        return self.category is PromptCategory.SCORED

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.prompt_id,
            "category": self.category.value,
            "prompt": self.prompt,
            "expect_contains": list(self.expect_contains),
        }
        if self.expect_exact is not None:
            payload["expect_exact"] = self.expect_exact
        return payload


@dataclass(frozen=True, slots=True)
class StudyControls:
    """Identity of one independently repeatable power-quality-v2 condition."""

    protocol_id: str
    host_role: HostRole
    condition_id: str
    launch_index: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "protocol_id": self.protocol_id,
            "host_role": self.host_role.value,
            "condition_id": self.condition_id,
            "launch_index": self.launch_index,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentLimits:
    """Fail-closed idle-state limits for a power-quality-v2 run."""

    idle_probe_seconds: float
    max_gpu_utilization_p95_percent: float
    max_start_temperature_c: int
    max_idle_vram_used_mib: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "idle_probe_seconds": self.idle_probe_seconds,
            "max_gpu_utilization_p95_percent": self.max_gpu_utilization_p95_percent,
            "max_start_temperature_c": self.max_start_temperature_c,
            "max_idle_vram_used_mib": self.max_idle_vram_used_mib,
        }


@dataclass(frozen=True, slots=True)
class InferenceOptions:
    """Runtime controls passed to Ollama and recorded in the manifest."""

    num_ctx: int = DEFAULT_NUM_CTX
    num_gpu: int = DEFAULT_NUM_GPU
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_INFERENCE_SEED
    num_predict: int | None = None
    kv_cache: str = DEFAULT_KV_CACHE

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_ctx": self.num_ctx,
            "num_gpu": self.num_gpu,
            "temperature": self.temperature,
            "seed": self.seed,
            "num_predict": self.num_predict,
            "kv_cache": self.kv_cache,
        }


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """A fully resolved, validated experiment definition."""

    experiment_id: str
    host_id: str
    output_dir: Path
    ollama_url: str
    models: tuple[str, ...]
    prompt_path: Path
    gpu_index: int
    telemetry_interval_ms: int
    warmup_requests: int
    repetitions: int
    order_seed: int
    concurrency: int
    options: InferenceOptions
    tariff_per_kwh: float | None
    currency: str | None
    source_path: Path
    expected_runtime_version: str | None = None
    expected_model_digests: dict[str, str] = field(default_factory=dict)
    study: StudyControls | None = None
    expected_power_limit_watts: float | None = None
    power_limit_tolerance_watts: float | None = None
    environment: EnvironmentLimits | None = None

    @property
    def cost_reporting_enabled(self) -> bool:
        """Cost is reported only against an explicit tariff; otherwise fields are null."""
        return self.tariff_per_kwh is not None and self.currency is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controls only.

        Absolute paths are deliberately excluded: they carry usernames and home
        directories, which must never reach a public artifact.
        """
        payload = {
            "experiment_id": self.experiment_id,
            "host_id": self.host_id,
            "ollama_url": self.ollama_url,
            "models": list(self.models),
            "expected_runtime_version": self.expected_runtime_version,
            "expected_model_digests": dict(self.expected_model_digests),
            "gpu_index": self.gpu_index,
            "telemetry_interval_ms": self.telemetry_interval_ms,
            "warmup_requests": self.warmup_requests,
            "repetitions": self.repetitions,
            "order_seed": self.order_seed,
            "concurrency": self.concurrency,
            "options": self.options.to_dict(),
            "tariff_per_kwh": self.tariff_per_kwh,
            "currency": self.currency,
        }
        if self.study is not None:
            payload["study"] = self.study.to_dict()
            payload["expected_power_limit_watts"] = self.expected_power_limit_watts
            payload["power_limit_tolerance_watts"] = self.power_limit_tolerance_watts
            payload["environment"] = (
                None if self.environment is None else self.environment.to_dict()
            )
        return payload

    def fingerprint(self) -> str:
        """Hash the controls so a run can be tied to the settings that produced it."""
        return _hash_payload(self.to_dict())


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

_SECTIONS: dict[str, set[str]] = {
    "experiment": {
        "id",
        "host_id",
        "output_dir",
        "repetitions",
        "warmup_requests",
        "order_seed",
    },
    "runtime": {"ollama_url", "models", "expected_version", "expected_digests"},
    "gpu": {
        "index",
        "telemetry_interval_ms",
        "expected_power_limit_watts",
        "power_limit_tolerance_watts",
    },
    "study": {"protocol_id", "host_role", "condition_id", "launch_index"},
    "environment": {
        "idle_probe_seconds",
        "max_gpu_utilization_p95_percent",
        "max_start_temperature_c",
        "max_idle_vram_used_mib",
    },
    "prompts": {"path"},
    "options": {
        "num_ctx",
        "num_gpu",
        "temperature",
        "seed",
        "num_predict",
        "kv_cache",
        "concurrency",
    },
    "cost": {"tariff_per_kwh", "currency"},
}
_REQUIRED_SECTIONS = ("experiment", "runtime", "prompts")


def load_config(path: Path | str) -> ExperimentConfig:
    """Load, validate, and resolve an experiment definition."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path.name}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path.name} is not valid TOML: {error}") from error
    except OSError as error:
        raise ConfigError(f"{path.name} could not be read: {error}") from error

    _reject_unknown(raw.keys(), _SECTIONS.keys(), "top-level section")
    for section in _REQUIRED_SECTIONS:
        if section not in raw:
            raise ConfigError(f"missing required section [{section}]")
    for name, allowed in _SECTIONS.items():
        _reject_unknown(raw.get(name, {}).keys(), allowed, f"key in [{name}]")

    experiment = raw["experiment"]
    runtime = raw["runtime"]
    gpu = raw.get("gpu", {})
    study, environment, expected_power_limit, power_limit_tolerance = _load_study_controls(
        raw.get("study"), raw.get("environment"), gpu
    )
    options_table = raw.get("options", {})
    cost = raw.get("cost", {})
    base = path.parent

    models = _as_list_of_str(runtime, "models", "runtime")
    if not models:
        raise ConfigError("[runtime] models must list at least one model tag")
    duplicates = sorted({m for m in models if models.count(m) > 1})
    if duplicates:
        raise ConfigError(f"[runtime] models contains duplicate entries: {', '.join(duplicates)}")
    expected_runtime_version = _optional_nonempty_str(runtime, "expected_version", "runtime")
    expected_model_digests = _expected_digests(runtime, models)

    concurrency = _as_int(options_table, "concurrency", "options", DEFAULT_CONCURRENCY)
    if concurrency != 1:
        raise ConfigError(
            "[options] concurrency must be 1: overlapping requests make per-request "
            "energy attribution meaningless"
        )

    return ExperimentConfig(
        experiment_id=_as_identifier(experiment, "id", "experiment"),
        host_id=_as_identifier(experiment, "host_id", "experiment"),
        output_dir=_as_path(experiment, "output_dir", "experiment", base),
        ollama_url=_as_url(runtime, "ollama_url", "runtime"),
        models=tuple(models),
        expected_runtime_version=expected_runtime_version,
        expected_model_digests=expected_model_digests,
        study=study,
        expected_power_limit_watts=expected_power_limit,
        power_limit_tolerance_watts=power_limit_tolerance,
        environment=environment,
        prompt_path=_as_path(raw["prompts"], "path", "prompts", base),
        gpu_index=_as_int(gpu, "index", "gpu", 0, minimum=0),
        telemetry_interval_ms=_as_int(
            gpu, "telemetry_interval_ms", "gpu", DEFAULT_TELEMETRY_INTERVAL_MS, minimum=1
        ),
        warmup_requests=_as_int(
            experiment, "warmup_requests", "experiment", DEFAULT_WARMUP_REQUESTS, minimum=0
        ),
        repetitions=_as_int(
            experiment, "repetitions", "experiment", DEFAULT_REPETITIONS, minimum=1
        ),
        order_seed=_as_int(experiment, "order_seed", "experiment", DEFAULT_ORDER_SEED),
        concurrency=concurrency,
        options=_load_options(options_table),
        **_load_cost(cost),
        source_path=path.resolve(),
    )


def _load_options(table: dict[str, Any]) -> InferenceOptions:
    kv_cache = _as_str(table, "kv_cache", "options", DEFAULT_KV_CACHE)
    if kv_cache not in SUPPORTED_KV_CACHE:
        raise ConfigError(
            f"[options] kv_cache must be one of {', '.join(SUPPORTED_KV_CACHE)}, got {kv_cache!r}"
        )

    num_predict = table.get("num_predict")
    if num_predict is not None:
        num_predict = _as_int(table, "num_predict", "options", minimum=1)

    return InferenceOptions(
        num_ctx=_as_int(table, "num_ctx", "options", DEFAULT_NUM_CTX, minimum=1),
        num_gpu=_as_int(table, "num_gpu", "options", DEFAULT_NUM_GPU, minimum=1),
        temperature=_as_float(table, "temperature", "options", DEFAULT_TEMPERATURE, minimum=0.0),
        seed=_as_int(table, "seed", "options", DEFAULT_INFERENCE_SEED),
        num_predict=num_predict,
        kv_cache=kv_cache,
    )


def _load_cost(table: dict[str, Any]) -> dict[str, Any]:
    """Resolve the optional tariff.

    Cost is only ever reported against an explicit tariff and currency; half a
    tariff is a mistake, not a default, because a fabricated currency would make
    a cost figure look authoritative when it is not.
    """
    tariff = table.get("tariff_per_kwh")
    currency = table.get("currency")

    if tariff is None and currency is None:
        return {"tariff_per_kwh": None, "currency": None}
    if tariff is None:
        raise ConfigError("[cost] currency is set but tariff_per_kwh is missing")
    if currency is None:
        raise ConfigError("[cost] tariff_per_kwh is set but currency is missing")

    return {
        "tariff_per_kwh": _as_float(table, "tariff_per_kwh", "cost", minimum=0.0),
        "currency": _as_identifier(table, "currency", "cost"),
    }


def _load_study_controls(
    study: dict[str, Any] | None,
    environment: dict[str, Any] | None,
    gpu: dict[str, Any],
) -> tuple[StudyControls | None, EnvironmentLimits | None, float | None, float | None]:
    power_keys_present = any(
        key in gpu for key in ("expected_power_limit_watts", "power_limit_tolerance_watts")
    )
    if study is None:
        if environment is not None or power_keys_present:
            raise ConfigError(
                "[study] is required when power-limit or environment controls are configured"
            )
        return None, None, None, None

    protocol_id = _as_identifier(study, "protocol_id", "study")
    if protocol_id != "power-quality-v2":
        raise ConfigError(f"[study]: protocol_id must be 'power-quality-v2', got {protocol_id!r}")

    raw_role = _as_str(study, "host_role", "study")
    try:
        host_role = HostRole(raw_role)
    except ValueError as error:
        raise ConfigError("[study]: host_role must be primary or external") from error

    launch_index = _as_int(study, "launch_index", "study", minimum=1)
    if launch_index > 3:
        raise ConfigError(f"[study]: launch_index must be between 1 and 3, got {launch_index}")

    expected_power_limit = _as_float(gpu, "expected_power_limit_watts", "gpu", minimum=0.0)
    if expected_power_limit <= 0:
        raise ConfigError("[gpu]: expected_power_limit_watts must be > 0")
    tolerance = _as_float(gpu, "power_limit_tolerance_watts", "gpu", minimum=0.0)
    if tolerance <= 0:
        raise ConfigError("[gpu]: power_limit_tolerance_watts must be > 0")
    if environment is None:
        raise ConfigError("missing required section [environment] for power-quality-v2")

    idle_probe_seconds = _as_float(environment, "idle_probe_seconds", "environment", minimum=0.0)
    if idle_probe_seconds <= 0:
        raise ConfigError("[environment]: idle_probe_seconds must be > 0")
    max_utilization = _as_float(
        environment,
        "max_gpu_utilization_p95_percent",
        "environment",
        minimum=0.0,
    )
    if max_utilization > 100:
        raise ConfigError("[environment]: max_gpu_utilization_p95_percent must be <= 100")

    limits = EnvironmentLimits(
        idle_probe_seconds=idle_probe_seconds,
        max_gpu_utilization_p95_percent=max_utilization,
        max_start_temperature_c=_as_int(
            environment, "max_start_temperature_c", "environment", minimum=0
        ),
        max_idle_vram_used_mib=_as_float(
            environment, "max_idle_vram_used_mib", "environment", minimum=0.0
        ),
    )
    controls = StudyControls(
        protocol_id=protocol_id,
        host_role=host_role,
        condition_id=_as_identifier(study, "condition_id", "study"),
        launch_index=launch_index,
    )
    return controls, limits, expected_power_limit, tolerance


def load_prompts(path: Path | str) -> tuple[PromptCase, ...]:
    """Load and validate a JSONL prompt set, preserving file order."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"prompt file not found: {path.name}")

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigError(f"{path.name} could not be read: {error}") from error

    prompts: list[PromptCase] = []
    seen: dict[str, int] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        prompt = _parse_prompt(line, number, path.name)
        if prompt.prompt_id in seen:
            raise ConfigError(
                f"{path.name} line {number}: duplicate prompt id {prompt.prompt_id!r}, "
                f"first seen on line {seen[prompt.prompt_id]}"
            )
        seen[prompt.prompt_id] = number
        prompts.append(prompt)

    if not prompts:
        raise ConfigError(f"{path.name} is empty: a prompt set needs at least one prompt")
    return tuple(prompts)


_PROMPT_FIELDS = {"id", "category", "prompt", "expect_contains", "expect_exact"}


def _parse_prompt(line: str, number: int, file_name: str) -> PromptCase:
    where = f"{file_name} line {number}"
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{where}: not valid JSON: {error.msg}") from error
    if not isinstance(record, dict):
        raise ConfigError(f"{where}: expected a JSON object")

    _reject_unknown(record.keys(), _PROMPT_FIELDS, f"field on {where}")

    prompt_id = _as_identifier(record, "id", where, bracket=False)

    raw_category = record.get("category")
    try:
        category = PromptCategory(raw_category)
    except ValueError as error:
        allowed = ", ".join(c.value for c in PromptCategory)
        raise ConfigError(
            f"{where}: category must be one of {allowed}, got {raw_category!r}"
        ) from error

    body = record.get("prompt")
    if not isinstance(body, str) or not body.strip():
        raise ConfigError(f"{where}: prompt must be a non-empty string")

    expect = record.get("expect_contains", [])
    if not isinstance(expect, list) or not all(isinstance(item, str) for item in expect):
        raise ConfigError(f"{where}: expect_contains must be a list of strings")
    raw_exact = record.get("expect_exact")
    if raw_exact is not None and (not isinstance(raw_exact, str) or not raw_exact.strip()):
        raise ConfigError(f"{where}: expect_exact must be a non-empty string")
    exact = raw_exact.strip() if isinstance(raw_exact, str) else None
    if category is PromptCategory.SCORED and bool(expect) == bool(exact):
        raise ConfigError(
            f"{where}: a scored prompt needs exactly one of expect_contains or expect_exact"
        )
    if category is not PromptCategory.SCORED and (expect or exact):
        raise ConfigError(
            f"{where}: expect_contains/expect_exact are only meaningful for scored prompts; "
            f"category is {category.value}"
        )

    return PromptCase(
        prompt_id=prompt_id,
        category=category,
        prompt=body,
        expect_contains=tuple(expect),
        expect_exact=exact,
    )


def prompts_fingerprint(prompts: tuple[PromptCase, ...]) -> str:
    """Hash a prompt set by content and order."""
    return _hash_payload([prompt.to_dict() for prompt in prompts])


# --------------------------------------------------------------------------
# Validators
# --------------------------------------------------------------------------


def _reject_unknown(present: Any, allowed: Any, what: str) -> None:
    unknown = sorted(set(present) - set(allowed))
    if unknown:
        raise ConfigError(f"unknown {what}: {', '.join(unknown)}")


def _missing(key: str, section: str, bracket: bool = True) -> ConfigError:
    where = f"[{section}]" if bracket else section
    return ConfigError(f"{where}: missing required key {key}")


def _wrong_type(
    key: str, section: str, expected: str, value: Any, bracket: bool = True
) -> ConfigError:
    where = f"[{section}]" if bracket else section
    return ConfigError(f"{where}: {key} must be {expected}, got {value!r}")


def _as_int(
    table: dict[str, Any],
    key: str,
    section: str,
    default: int | None = None,
    *,
    minimum: int | None = None,
) -> int:
    value = table.get(key, default)
    if value is None:
        raise _missing(key, section)
    # bool is an int subclass; accepting it here would silently turn True into 1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise _wrong_type(key, section, "an integer", value)
    if minimum is not None and value < minimum:
        raise ConfigError(f"[{section}]: {key} must be >= {minimum}, got {value}")
    return value


def _as_float(
    table: dict[str, Any],
    key: str,
    section: str,
    default: float | None = None,
    *,
    minimum: float | None = None,
) -> float:
    value = table.get(key, default)
    if value is None:
        raise _missing(key, section)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _wrong_type(key, section, "a number", value)
    if minimum is not None and value < minimum:
        raise ConfigError(f"[{section}]: {key} must be >= {minimum}, got {value}")
    return float(value)


def _as_str(table: dict[str, Any], key: str, section: str, default: str | None = None) -> str:
    value = table.get(key, default)
    if value is None:
        raise _missing(key, section)
    if not isinstance(value, str):
        raise _wrong_type(key, section, "a string", value)
    return value


def _as_identifier(table: dict[str, Any], key: str, section: str, *, bracket: bool = True) -> str:
    value = table.get(key)
    if value is None:
        raise _missing(key, section, bracket)
    if not isinstance(value, str):
        raise _wrong_type(key, section, "a string", value, bracket)
    if not IDENTIFIER_PATTERN.match(value):
        where = f"[{section}]" if bracket else section
        raise ConfigError(
            f"{where}: {key} must contain only letters, digits, dot, dash, or underscore "
            f"and start with a letter or digit, got {value!r}"
        )
    return value


def _as_list_of_str(table: dict[str, Any], key: str, section: str) -> list[str]:
    value = table.get(key)
    if value is None:
        raise _missing(key, section)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _wrong_type(key, section, "a list of strings", value)
    return value


def _as_url(table: dict[str, Any], key: str, section: str) -> str:
    value = _as_str(table, key, section)
    if not value.startswith(("http://", "https://")):
        raise ConfigError(f"[{section}]: {key} must start with http:// or https://, got {value!r}")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError(f"[{section}]: {key} must not contain credentials")
    if not parsed.hostname:
        raise ConfigError(f"[{section}]: {key} must contain a host, got {value!r}")
    return value.rstrip("/")


def _optional_nonempty_str(table: dict[str, Any], key: str, section: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _wrong_type(key, section, "a non-empty string", value)
    return value.strip()


def _expected_digests(table: dict[str, Any], models: list[str]) -> dict[str, str]:
    value = table.get("expected_digests")
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and isinstance(digest, str) for name, digest in value.items()
    ):
        raise _wrong_type(
            "expected_digests", "runtime", "a table mapping model names to SHA-256 strings", value
        )
    if set(value) != set(models):
        raise ConfigError("[runtime]: expected_digests must cover exactly the configured models")
    invalid = sorted(name for name, digest in value.items() if not SHA256_PATTERN.fullmatch(digest))
    if invalid:
        raise ConfigError(
            "[runtime]: expected_digests values must be full 64-character SHA-256 hex strings; "
            f"invalid models: {', '.join(invalid)}"
        )
    return {name: digest.lower() for name, digest in value.items()}


def _as_path(table: dict[str, Any], key: str, section: str, base: Path) -> Path:
    """Resolve a path against the config file, so a config is portable."""
    return (base / _as_str(table, key, section)).resolve()


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
