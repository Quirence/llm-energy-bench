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
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

DEFAULT_WARMUP_REQUESTS = 2
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


@dataclass(frozen=True, slots=True)
class PromptCase:
    """One prompt, identified by a stable ID that survives into every artifact."""

    prompt_id: str
    category: PromptCategory
    prompt: str
    expect_contains: tuple[str, ...] = ()

    @property
    def is_scored(self) -> bool:
        return self.category is PromptCategory.SCORED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.prompt_id,
            "category": self.category.value,
            "prompt": self.prompt,
            "expect_contains": list(self.expect_contains),
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

    @property
    def cost_reporting_enabled(self) -> bool:
        """Cost is reported only against an explicit tariff; otherwise fields are null."""
        return self.tariff_per_kwh is not None and self.currency is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controls only.

        Absolute paths are deliberately excluded: they carry usernames and home
        directories, which must never reach a public artifact.
        """
        return {
            "experiment_id": self.experiment_id,
            "host_id": self.host_id,
            "ollama_url": self.ollama_url,
            "models": list(self.models),
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
    "runtime": {"ollama_url", "models"},
    "gpu": {"index", "telemetry_interval_ms"},
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
    options_table = raw.get("options", {})
    cost = raw.get("cost", {})
    base = path.parent

    models = _as_list_of_str(runtime, "models", "runtime")
    if not models:
        raise ConfigError("[runtime] models must list at least one model tag")
    duplicates = sorted({m for m in models if models.count(m) > 1})
    if duplicates:
        raise ConfigError(f"[runtime] models contains duplicate entries: {', '.join(duplicates)}")

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


_PROMPT_FIELDS = {"id", "category", "prompt", "expect_contains"}


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
    if category is PromptCategory.SCORED and not expect:
        raise ConfigError(
            f"{where}: a scored prompt needs a non-empty expect_contains; "
            "without it the quality floor cannot be applied"
        )
    if category is not PromptCategory.SCORED and expect:
        raise ConfigError(
            f"{where}: expect_contains is only meaningful for scored prompts; "
            f"category is {category.value}"
        )

    return PromptCase(
        prompt_id=prompt_id,
        category=category,
        prompt=body,
        expect_contains=tuple(expect),
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
    return value.rstrip("/")


def _as_path(table: dict[str, Any], key: str, section: str, base: Path) -> Path:
    """Resolve a path against the config file, so a config is portable."""
    return (base / _as_str(table, key, section)).resolve()


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
