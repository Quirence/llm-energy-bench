"""Tests for the experiment configuration and prompt-set contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_energy_bench.config import (
    ConfigError,
    PromptCategory,
    load_config,
    load_prompts,
    prompts_fingerprint,
)

VALID_CONFIG = """
[experiment]
id = "pilot-rtx3050"
host_id = "host-a"
output_dir = "experiments/runs"
repetitions = 3
warmup_requests = 2
order_seed = 42

[runtime]
ollama_url = "http://127.0.0.1:11434"
models = ["llama3.2:3b-instruct-q4_K_M"]

[gpu]
index = 0
telemetry_interval_ms = 100

[prompts]
path = "prompts/pilot-v1.jsonl"

[options]
num_ctx = 4096
num_gpu = 999
temperature = 0.0
seed = 42
num_predict = 256
kv_cache = "f16"
concurrency = 1
"""


def write_config(tmp_path: Path, body: str = VALID_CONFIG) -> Path:
    path = tmp_path / "experiment.toml"
    path.write_text(body, encoding="utf-8")
    return path


def replace(body: str, old: str, new: str) -> str:
    assert old in body, f"fixture no longer contains {old!r}"
    return body.replace(old, new)


# --------------------------------------------------------------------------
# Valid configuration
# --------------------------------------------------------------------------


def test_a_valid_config_loads_every_field(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert config.experiment_id == "pilot-rtx3050"
    assert config.host_id == "host-a"
    assert config.repetitions == 3
    assert config.warmup_requests == 2
    assert config.order_seed == 42
    assert config.ollama_url == "http://127.0.0.1:11434"
    assert config.models == ("llama3.2:3b-instruct-q4_K_M",)
    assert config.gpu_index == 0
    assert config.telemetry_interval_ms == 100
    assert config.options.num_ctx == 4096
    assert config.options.num_gpu == 999
    assert config.options.temperature == 0.0
    assert config.options.seed == 42
    assert config.options.num_predict == 256
    assert config.options.kv_cache == "f16"
    assert config.concurrency == 1


def test_paths_resolve_against_the_config_file_not_the_working_directory(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "configs"
    nested.mkdir()
    path = nested / "experiment.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_config(path)

    assert config.prompt_path == (nested / "prompts/pilot-v1.jsonl").resolve()
    assert config.output_dir == (nested / "experiments/runs").resolve()


def test_defaults_match_the_approved_reproducibility_controls(tmp_path: Path) -> None:
    minimal = """
[experiment]
id = "e"
host_id = "h"
output_dir = "out"

[runtime]
ollama_url = "http://127.0.0.1:11434"
models = ["m"]

[prompts]
path = "p.jsonl"
"""
    config = load_config(write_config(tmp_path, minimal))

    assert config.warmup_requests == 2
    assert config.telemetry_interval_ms == 100
    assert config.concurrency == 1
    assert config.options.num_ctx == 4096
    assert config.options.num_gpu == 999
    assert config.options.temperature == 0.0
    assert config.options.seed == 42
    assert config.options.kv_cache == "f16"
    assert config.gpu_index == 0


def test_the_resolved_config_is_hashable_and_serializable(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))
    payload = json.dumps(config.to_dict(), sort_keys=True)

    assert json.loads(payload)["experiment_id"] == "pilot-rtx3050"
    assert config.fingerprint() == load_config(write_config(tmp_path)).fingerprint()


def test_a_changed_control_changes_the_config_fingerprint(tmp_path: Path) -> None:
    """A run made under different controls must not hash the same."""
    first = load_config(write_config(tmp_path))

    other = tmp_path / "other"
    other.mkdir()
    changed = replace(VALID_CONFIG, "num_ctx = 4096", "num_ctx = 8192")
    second = load_config(write_config(other, changed))

    assert first.fingerprint() != second.fingerprint()


# --------------------------------------------------------------------------
# Rejected configuration
# --------------------------------------------------------------------------


def test_a_missing_config_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")


def test_malformed_toml_is_rejected_with_the_file_named(tmp_path: Path) -> None:
    path = tmp_path / "experiment.toml"
    path.write_text("[experiment\nid = ", encoding="utf-8")

    with pytest.raises(ConfigError, match="experiment.toml"):
        load_config(path)


def test_an_unknown_top_level_section_is_rejected(tmp_path: Path) -> None:
    body = VALID_CONFIG + "\n[telemetry]\nmode = 'fast'\n"

    with pytest.raises(ConfigError, match="telemetry"):
        load_config(write_config(tmp_path, body))


def test_an_unknown_key_inside_a_section_is_rejected(tmp_path: Path) -> None:
    body = replace(VALID_CONFIG, 'id = "pilot-rtx3050"', 'id = "pilot-rtx3050"\nnotes = "x"')

    with pytest.raises(ConfigError, match="notes"):
        load_config(write_config(tmp_path, body))


def test_a_missing_required_key_is_rejected(tmp_path: Path) -> None:
    body = replace(VALID_CONFIG, 'host_id = "host-a"\n', "")

    with pytest.raises(ConfigError, match="host_id"):
        load_config(write_config(tmp_path, body))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("repetitions = 3", "repetitions = 0", "repetitions"),
        ("warmup_requests = 2", "warmup_requests = -1", "warmup_requests"),
        ("telemetry_interval_ms = 100", "telemetry_interval_ms = 0", "telemetry_interval_ms"),
        ("index = 0", "index = -1", "index"),
        ("num_ctx = 4096", "num_ctx = 0", "num_ctx"),
        ("num_gpu = 999", "num_gpu = 0", "num_gpu"),
        ("temperature = 0.0", "temperature = -0.5", "temperature"),
        ("num_predict = 256", "num_predict = 0", "num_predict"),
    ],
)
def test_out_of_range_values_are_rejected(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, replace(VALID_CONFIG, old, new)))


def test_concurrency_above_one_is_rejected(tmp_path: Path) -> None:
    """Parallel requests would make per-request energy attribution meaningless."""
    body = replace(VALID_CONFIG, "concurrency = 1", "concurrency = 4")

    with pytest.raises(ConfigError, match="concurrency"):
        load_config(write_config(tmp_path, body))


def test_an_empty_model_list_is_rejected(tmp_path: Path) -> None:
    body = replace(VALID_CONFIG, 'models = ["llama3.2:3b-instruct-q4_K_M"]', "models = []")

    with pytest.raises(ConfigError, match="models"):
        load_config(write_config(tmp_path, body))


def test_duplicate_models_are_rejected(tmp_path: Path) -> None:
    body = replace(
        VALID_CONFIG,
        'models = ["llama3.2:3b-instruct-q4_K_M"]',
        'models = ["a", "a"]',
    )

    with pytest.raises(ConfigError, match="duplicate"):
        load_config(write_config(tmp_path, body))


def test_a_non_http_ollama_url_is_rejected(tmp_path: Path) -> None:
    body = replace(
        VALID_CONFIG, 'ollama_url = "http://127.0.0.1:11434"', 'ollama_url = "127.0.0.1"'
    )

    with pytest.raises(ConfigError, match="ollama_url"):
        load_config(write_config(tmp_path, body))


@pytest.mark.parametrize("identifier", ["has space", "имя", "a/b", ""])
def test_identifiers_must_be_safe_for_paths_and_public_artifacts(
    tmp_path: Path, identifier: str
) -> None:
    body = replace(VALID_CONFIG, 'id = "pilot-rtx3050"', f'id = "{identifier}"')

    with pytest.raises(ConfigError, match="id"):
        load_config(write_config(tmp_path, body))


def test_a_wrongly_typed_value_is_rejected(tmp_path: Path) -> None:
    body = replace(VALID_CONFIG, "repetitions = 3", 'repetitions = "three"')

    with pytest.raises(ConfigError, match="repetitions"):
        load_config(write_config(tmp_path, body))


# --------------------------------------------------------------------------
# Tariff semantics
# --------------------------------------------------------------------------


def test_without_a_cost_section_both_tariff_and_currency_are_null(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert config.tariff_per_kwh is None
    assert config.currency is None
    assert config.cost_reporting_enabled is False


def test_a_complete_cost_section_enables_cost_reporting(tmp_path: Path) -> None:
    body = VALID_CONFIG + '\n[cost]\ntariff_per_kwh = 5.5\ncurrency = "RUB"\n'
    config = load_config(write_config(tmp_path, body))

    assert config.tariff_per_kwh == pytest.approx(5.5)
    assert config.currency == "RUB"
    assert config.cost_reporting_enabled is True


def test_a_tariff_without_a_currency_is_rejected(tmp_path: Path) -> None:
    body = VALID_CONFIG + "\n[cost]\ntariff_per_kwh = 5.5\n"

    with pytest.raises(ConfigError, match="currency"):
        load_config(write_config(tmp_path, body))


def test_a_currency_without_a_tariff_is_rejected(tmp_path: Path) -> None:
    body = VALID_CONFIG + '\n[cost]\ncurrency = "RUB"\n'

    with pytest.raises(ConfigError, match="tariff_per_kwh"):
        load_config(write_config(tmp_path, body))


def test_a_negative_tariff_is_rejected(tmp_path: Path) -> None:
    body = VALID_CONFIG + '\n[cost]\ntariff_per_kwh = -1.0\ncurrency = "RUB"\n'

    with pytest.raises(ConfigError, match="tariff_per_kwh"):
        load_config(write_config(tmp_path, body))


# --------------------------------------------------------------------------
# Prompt sets
# --------------------------------------------------------------------------

SHORT = {"id": "short-01", "category": "short", "prompt": "Name one primary colour."}
LONG = {"id": "long-01", "category": "long", "prompt": "Summarise: " + "context " * 50}
SCORED = {
    "id": "scored-01",
    "category": "scored",
    "prompt": "What is 2 + 2? Answer with the number only.",
    "expect_contains": ["4"],
}


def write_prompts(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "prompts.jsonl"
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_a_valid_prompt_set_loads_in_file_order(tmp_path: Path) -> None:
    prompts = load_prompts(write_prompts(tmp_path, SHORT, LONG, SCORED))

    assert [p.prompt_id for p in prompts] == ["short-01", "long-01", "scored-01"]
    assert prompts[0].category is PromptCategory.SHORT
    assert prompts[1].category is PromptCategory.LONG
    assert prompts[2].category is PromptCategory.SCORED
    assert prompts[2].expect_contains == ("4",)


def test_unscored_prompts_carry_no_expectations(tmp_path: Path) -> None:
    prompts = load_prompts(write_prompts(tmp_path, SHORT))

    assert prompts[0].expect_contains == ()
    assert prompts[0].is_scored is False


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "prompts.jsonl"
    path.write_text(f"\n{json.dumps(SHORT)}\n\n{json.dumps(LONG)}\n\n", encoding="utf-8")

    assert len(load_prompts(path)) == 2


def test_a_missing_prompt_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_prompts(tmp_path / "absent.jsonl")


def test_an_empty_prompt_set_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "prompts.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="empty"):
        load_prompts(path)


def test_duplicate_prompt_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="short-01"):
        load_prompts(write_prompts(tmp_path, SHORT, dict(SHORT)))


def test_a_scored_prompt_without_expectations_is_rejected(tmp_path: Path) -> None:
    broken = {k: v for k, v in SCORED.items() if k != "expect_contains"}

    with pytest.raises(ConfigError, match="expect_contains"):
        load_prompts(write_prompts(tmp_path, broken))


def test_a_scored_prompt_with_empty_expectations_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="expect_contains"):
        load_prompts(write_prompts(tmp_path, {**SCORED, "expect_contains": []}))


def test_an_unscored_prompt_with_expectations_is_rejected(tmp_path: Path) -> None:
    """Silently ignored expectations would misreport the quality floor."""
    with pytest.raises(ConfigError, match="expect_contains"):
        load_prompts(write_prompts(tmp_path, {**SHORT, "expect_contains": ["red"]}))


def test_an_unknown_category_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="category"):
        load_prompts(write_prompts(tmp_path, {**SHORT, "category": "medium"}))


def test_an_unknown_prompt_field_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="weight"):
        load_prompts(write_prompts(tmp_path, {**SHORT, "weight": 2}))


def test_an_empty_prompt_body_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="prompt"):
        load_prompts(write_prompts(tmp_path, {**SHORT, "prompt": "   "}))


def test_malformed_json_names_the_offending_line(tmp_path: Path) -> None:
    path = tmp_path / "prompts.jsonl"
    path.write_text(f"{json.dumps(SHORT)}\n{{not json}}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="line 2"):
        load_prompts(path)


def test_the_prompt_set_hash_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    """The manifest identifies a prompt set by content, not by file path."""
    second_dir = tmp_path / "b"
    second_dir.mkdir()
    third_dir = tmp_path / "c"
    third_dir.mkdir()

    first = load_prompts(write_prompts(tmp_path, SHORT, LONG))
    same = load_prompts(write_prompts(second_dir, SHORT, LONG))
    edited = load_prompts(write_prompts(third_dir, SHORT, {**LONG, "prompt": "different"}))

    assert prompts_fingerprint(first) == prompts_fingerprint(same)
    assert prompts_fingerprint(first) != prompts_fingerprint(edited)


def test_reordering_a_prompt_set_changes_its_hash(tmp_path: Path) -> None:
    """Order is part of the contract: it seeds the deterministic run order."""
    second_dir = tmp_path / "b"
    second_dir.mkdir()

    forward = load_prompts(write_prompts(tmp_path, SHORT, LONG))
    backward = load_prompts(write_prompts(second_dir, LONG, SHORT))

    assert prompts_fingerprint(forward) != prompts_fingerprint(backward)


# --------------------------------------------------------------------------
# Shipped pilot artifacts
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_shipped_pilot_config_is_valid() -> None:
    config = load_config(REPO_ROOT / "configs" / "pilot.toml")

    assert config.repetitions == 3
    assert config.models == ("llama3.2:3b-instruct-q4_K_M",)
    assert config.warmup_requests == 2
    assert config.options.num_gpu == 999
    assert config.cost_reporting_enabled is False


def test_the_shipped_pilot_prompt_set_matches_the_approved_shape() -> None:
    prompts = load_prompts(REPO_ROOT / "prompts" / "pilot-v1.jsonl")

    assert len(prompts) == 6
    by_category = {c: [p for p in prompts if p.category is c] for c in PromptCategory}
    assert len(by_category[PromptCategory.SHORT]) == 2
    assert len(by_category[PromptCategory.LONG]) == 2
    assert len(by_category[PromptCategory.SCORED]) == 2


def test_the_pilot_produces_the_eighteen_records_task_8_expects() -> None:
    config = load_config(REPO_ROOT / "configs" / "pilot.toml")
    prompts = load_prompts(config.prompt_path)

    assert len(prompts) * config.repetitions * len(config.models) == 18


# --------------------------------------------------------------------------
# Frozen benchmark-v1 artifacts
# --------------------------------------------------------------------------

BENCHMARK_MODELS = (
    "qwen3:4b-instruct-2507-q4_K_M",
    "qwen3:4b-instruct-2507-q8_0",
    "llama3.2:3b-instruct-q4_K_M",
    "llama3.2:3b-instruct-q8_0",
)


def test_benchmark_v1_config_freezes_the_approved_matrix() -> None:
    config = load_config(REPO_ROOT / "configs" / "benchmark-v1.toml")

    assert config.experiment_id == "benchmark-v1"
    assert config.models == BENCHMARK_MODELS
    assert config.repetitions == 5
    assert config.warmup_requests == 2
    assert config.telemetry_interval_ms == 100
    assert config.options.num_ctx == 4096
    assert config.options.num_gpu == 999
    assert config.options.temperature == 0.0
    assert config.options.seed == 42
    assert config.options.kv_cache == "f16"
    assert config.concurrency == 1
    assert config.cost_reporting_enabled is False


def test_benchmark_v1_has_eight_unique_prompts_per_category() -> None:
    prompts = load_prompts(REPO_ROOT / "prompts" / "benchmark-v1.jsonl")

    assert len(prompts) == 24
    assert len({prompt.prompt_id for prompt in prompts}) == 24
    by_category = {c: [p for p in prompts if p.category is c] for c in PromptCategory}
    assert {category: len(items) for category, items in by_category.items()} == {
        PromptCategory.SHORT: 8,
        PromptCategory.LONG: 8,
        PromptCategory.SCORED: 8,
    }


def test_benchmark_v1_workload_size_is_fixed() -> None:
    config = load_config(REPO_ROOT / "configs" / "benchmark-v1.toml")
    prompts = load_prompts(config.prompt_path)

    assert len(prompts) * config.repetitions * len(config.models) == 480
