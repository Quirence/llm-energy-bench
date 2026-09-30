"""Tests for immutable run artifacts: atomic writes, integrity, and privacy."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from llm_energy_bench.results import (
    MAX_ARTIFACT_BYTES,
    REQUIRED_RAW_ARTIFACTS,
    VALIDATION,
    WARMUPS,
    GzipJsonlWriter,
    JsonlWriter,
    PrivacyError,
    ResultsError,
    RunStatus,
    assert_public_safe,
    create_run_dir,
    read_gzip_jsonl,
    read_jsonl,
    scan_for_private_data,
    sha256_bytes,
    sha256_file,
    validate_run,
    write_json,
    write_text,
)

# --------------------------------------------------------------------------
# Atomic writes
# --------------------------------------------------------------------------


def test_write_json_produces_readable_utf8(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    write_json(target, {"model": "qwen3:4b", "note": "тест"})

    assert json.loads(target.read_text(encoding="utf-8"))["note"] == "тест"


def test_write_json_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    write_json(tmp_path / "manifest.json", {"a": 1})

    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_a_failed_write_preserves_the_previous_content(tmp_path: Path) -> None:
    """A half-written artifact must never replace a good one."""
    target = tmp_path / "manifest.json"
    write_json(target, {"good": True})

    with pytest.raises(ResultsError):
        write_json(target, {"bad": {1, 2, 3}})  # a set is not JSON-serializable

    assert json.loads(target.read_text(encoding="utf-8")) == {"good": True}
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_write_text_is_atomic_too(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    write_text(target, "# Report\n")

    assert target.read_text(encoding="utf-8") == "# Report\n"


def test_write_json_is_deterministic_for_equal_payloads(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    write_json(first, {"b": 2, "a": 1})
    write_json(second, {"a": 1, "b": 2})

    assert sha256_file(first) == sha256_file(second)


# --------------------------------------------------------------------------
# JSONL and gzip JSONL
# --------------------------------------------------------------------------


def test_jsonl_records_round_trip_in_order(tmp_path: Path) -> None:
    target = tmp_path / "requests.jsonl"
    with JsonlWriter(target) as writer:
        for index in range(3):
            writer.write({"request_id": f"r{index}"})

    assert [r["request_id"] for r in read_jsonl(target)] == ["r0", "r1", "r2"]


def test_each_jsonl_record_reaches_disk_immediately(tmp_path: Path) -> None:
    """An interrupted run must still be auditable, so nothing is buffered."""
    target = tmp_path / "requests.jsonl"
    with JsonlWriter(target) as writer:
        writer.write({"request_id": "r0"})
        assert [r["request_id"] for r in read_jsonl(target)] == ["r0"]
        writer.write({"request_id": "r1"})
        assert len(read_jsonl(target)) == 2


def test_gzip_jsonl_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "telemetry.jsonl.gz"
    with GzipJsonlWriter(target) as writer:
        for index in range(100):
            writer.write({"sample": index})

    assert [r["sample"] for r in read_gzip_jsonl(target)] == list(range(100))
    assert gzip.decompress(target.read_bytes())


def test_telemetry_compresses_substantially(tmp_path: Path) -> None:
    target = tmp_path / "telemetry.jsonl.gz"
    sample = {"power_instant_watts": 45.0, "temperature_c": 63, "request_id": "req-0001"}
    with GzipJsonlWriter(target) as writer:
        for _ in range(500):
            writer.write(sample)

    raw_size = len(json.dumps(sample).encode("utf-8") + b"\n") * 500
    assert target.stat().st_size < raw_size / 5


def test_a_truncated_gzip_stream_still_yields_its_records(tmp_path: Path) -> None:
    """Ctrl+C leaves a gzip file without its trailer; the samples must survive."""
    target = tmp_path / "telemetry.jsonl.gz"
    writer = GzipJsonlWriter(target)
    for index in range(50):
        writer.write({"sample": index})
    # Deliberately never closed: this is what an interrupted run leaves behind.

    recovered = read_gzip_jsonl(target, tolerate_truncation=True)

    assert len(recovered) >= 40
    assert [r["sample"] for r in recovered] == list(range(len(recovered)))


def test_a_truncated_gzip_stream_is_an_error_when_not_tolerated(tmp_path: Path) -> None:
    target = tmp_path / "telemetry.jsonl.gz"
    writer = GzipJsonlWriter(target)
    writer.write({"sample": 0})

    with pytest.raises(ResultsError):
        read_gzip_jsonl(target)


def test_a_malformed_jsonl_line_names_its_position(tmp_path: Path) -> None:
    target = tmp_path / "requests.jsonl"
    target.write_text('{"a": 1}\n{oops}\n', encoding="utf-8")

    with pytest.raises(ResultsError, match="line 2"):
        read_jsonl(target)


# --------------------------------------------------------------------------
# Checksums
# --------------------------------------------------------------------------


def test_sha256_helpers_agree(tmp_path: Path) -> None:
    payload = b"telemetry"
    target = tmp_path / "f.bin"
    target.write_bytes(payload)

    assert sha256_file(target) == sha256_bytes(payload)
    assert len(sha256_file(target)) == 64


def test_a_changed_byte_changes_the_checksum(tmp_path: Path) -> None:
    target = tmp_path / "f.bin"
    target.write_bytes(b"a")
    before = sha256_file(target)
    target.write_bytes(b"b")

    assert sha256_file(target) != before


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


# Token-shaped fixtures are assembled at runtime. A literal secret in a test
# file is still a secret: it trips push protection and, worse, teaches the next
# reader that pasting a real one here is acceptable.
FAKE_GITHUB_TOKEN = "ghp" + "_" + "A" * 36
FAKE_GITHUB_PAT = "github" + "_pat_" + "1" * 22
FAKE_API_KEY = "sk" + "-" + "z" * 24
FAKE_AWS_KEY = "AKIA" + "Q" * 16


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\Lev\models\llama.gguf",
        "C:/Users/Lev/AppData/Local/Ollama",
        "/home/lcatharsis/llm-energy-bench",
        "/Users/lev/Library/Caches",
        "GPU-12345678-90ab-cdef-1234-567890abcdef",
        FAKE_GITHUB_TOKEN,
        FAKE_GITHUB_PAT,
        FAKE_API_KEY,
        FAKE_AWS_KEY,
    ],
)
def test_private_values_are_detected(value: str) -> None:
    assert scan_for_private_data(value)


@pytest.mark.parametrize(
    "value",
    [
        "llama3.2:3b-instruct-q4_K_M",
        "NVIDIA GeForce RTX 3050 Laptop GPU",
        "experiments/runs/pilot-rtx3050",
        "54a50433af3c357a",
        "http://127.0.0.1:11434",
    ],
)
def test_ordinary_values_are_not_flagged(value: str) -> None:
    assert scan_for_private_data(value) == ()


def test_a_manifest_with_a_windows_path_is_rejected_before_it_is_written(
    tmp_path: Path,
) -> None:
    manifest = {"host": {"model_path": r"C:\Users\Lev\.ollama\models"}}

    with pytest.raises(PrivacyError) as caught:
        assert_public_safe(manifest)

    assert "host.model_path" in str(caught.value)


def test_private_data_is_found_inside_nested_lists_and_keys() -> None:
    payload = {"gpus": [{"uuid": "GPU-12345678-90ab-cdef-1234-567890abcdef"}]}

    with pytest.raises(PrivacyError, match=r"gpus\[0\].uuid"):
        assert_public_safe(payload)


def test_the_current_username_is_rejected_even_in_an_unusual_place() -> None:
    import getpass

    user = getpass.getuser()
    with pytest.raises(PrivacyError):
        assert_public_safe({"note": f"run performed by {user}"})


def test_credentials_in_a_url_are_rejected_by_the_public_artifact_scanner() -> None:
    with pytest.raises(PrivacyError, match="URL credentials"):
        assert_public_safe({"ollama_url": "http://alice:secret@example.test:11434"})


def test_a_clean_manifest_passes() -> None:
    assert_public_safe(
        {
            "gpu": {"name": "NVIDIA GeForce RTX 3050 Laptop GPU", "fingerprint": "54a50433af3c"},
            "models": ["llama3.2:3b-instruct-q4_K_M"],
            "energy_source": "total_energy_counter",
            "power_limit_watts": 60.0,
            "tariff_per_kwh": None,
        }
    )


# --------------------------------------------------------------------------
# Run directories
# --------------------------------------------------------------------------


def test_a_run_directory_gets_a_unique_identifier(tmp_path: Path) -> None:
    first = create_run_dir(tmp_path, "pilot-rtx3050", "host-a")
    second = create_run_dir(tmp_path, "pilot-rtx3050", "host-a")

    assert first != second
    assert first.is_dir() and second.is_dir()
    assert first.name.startswith("pilot-rtx3050-host-a-")


def test_a_run_is_never_resumed_in_place(tmp_path: Path) -> None:
    """A retry gets a new identifier, so an existing run can never be overwritten."""
    existing = create_run_dir(tmp_path, "e", "h")
    write_json(existing / "manifest.json", {"status": "interrupted"})

    retry = create_run_dir(tmp_path, "e", "h")

    assert retry != existing
    assert json.loads((existing / "manifest.json").read_text())["status"] == "interrupted"


def test_a_run_identifier_carries_no_private_data(tmp_path: Path) -> None:
    run_dir = create_run_dir(tmp_path, "pilot", "host-a")

    assert scan_for_private_data(run_dir.name) == ()


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def complete_run(tmp_path: Path, status: RunStatus = RunStatus.COMPLETED) -> Path:
    run_dir = create_run_dir(tmp_path, "e", "h")
    digest = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
    write_json(
        run_dir / "manifest.json",
        {
            "schema_version": 1,
            "run_id": run_dir.name,
            "status": status.value,
            "models": [
                {
                    "name": "llama3.2:3b-instruct-q4_K_M",
                    "digest": digest,
                    "fully_on_gpu": True,
                }
            ],
        },
    )
    write_text(run_dir / "config.resolved.toml", '[experiment]\nid = "e"\n')
    with JsonlWriter(run_dir / "requests.jsonl") as writer:
        writer.write({"request_id": "r0", "valid": True})
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(
            {
                "request_id": "r0",
                "model": "llama3.2:3b-instruct-q4_K_M",
                "model_digest": digest,
                "valid": True,
                "prompt_eval_cached_count": 0,
                "metrics": {
                    "gpu_energy_joules": 12.0,
                    "max_telemetry_gap_seconds": 0.1,
                },
            }
        )
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "r0", "monotonic_s": 0.0})
        writer.write({"request_id": "r0", "monotonic_s": 0.1})
    return run_dir


def schema_v1_run(tmp_path: Path) -> Path:
    return complete_run(tmp_path)


def schema_v2_run(tmp_path: Path) -> Path:
    run_dir = create_run_dir(tmp_path, "e", "h")
    digest = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
    write_text(run_dir / "config.resolved.toml", '[experiment]\nid = "e"\n')
    with JsonlWriter(run_dir / WARMUPS) as writer:
        for index, cached in enumerate((40, 21, 20, 21), start=1):
            writer.write(
                {
                    "request_id": f"w{index}",
                    "model": "llama3.2:3b-instruct-q4_K_M",
                    "model_digest": digest,
                    "warmup_index": index,
                    "prompt_id": "p0",
                    "valid": True,
                    "prompt_eval_count": 50,
                    "prompt_eval_cached_count": cached,
                    "load_duration_ns": 10_000_000,
                }
            )
    with JsonlWriter(run_dir / "requests.jsonl") as writer:
        writer.write({"request_id": "r0", "model_digest": digest})
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(
            {
                "request_id": "r0",
                "model": "llama3.2:3b-instruct-q4_K_M",
                "model_digest": digest,
                "valid": True,
                "invalid_reasons": [],
                "latency_s": 2.0,
                "ttft_s": 0.2,
                "prompt_eval_count": 26,
                "prompt_eval_cached_count": 21,
                "eval_count": 4,
                "total_duration_ns": 2_000_000_000,
                "load_duration_ns": 10_000_000,
                "prompt_eval_duration_ns": 1_000_000_000,
                "eval_duration_ns": 900_000_000,
                "metrics": {
                    "gpu_energy_joules": 12.0,
                    "telemetry_sample_count": 2,
                    "max_telemetry_gap_seconds": 0.1,
                    "template_cache_baseline_tokens": 20,
                    "excess_cached_prompt_tokens": 1,
                    "uncached_prompt_tokens": 5,
                },
            }
        )
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "r0", "monotonic_s": 0.0})
        writer.write({"request_id": "r0", "monotonic_s": 0.1})
    manifest = {
        "schema_version": 2,
        "run_id": run_dir.name,
        "status": "completed",
        "host_id": "host-a",
        "runtime": {"name": "ollama", "version": "0.34.2"},
        "prompt_cache_policy": "template_floor_v2",
        "cache_buster_policy": "uuid_prefix_v1",
        "max_cache_excess_tokens": 1,
        "max_measured_load_duration_ns": 100_000_000,
        "prompt_count": 1,
        "repetitions": 1,
        "completed_warmups": 4,
        "started_requests": 1,
        "completed_requests": 1,
        "valid_requests": 1,
        "models": [
            {
                "name": "llama3.2:3b-instruct-q4_K_M",
                "digest": digest,
                "fully_on_gpu": True,
                "template_cache_baseline_tokens": 20,
            }
        ],
        "controls": {
            "models": ["llama3.2:3b-instruct-q4_K_M"],
            "warmup_requests": 4,
            "repetitions": 1,
            "expected_runtime_version": "0.34.2",
            "expected_model_digests": {"llama3.2:3b-instruct-q4_K_M": digest},
        },
        "config_sha256": sha256_file(run_dir / "config.resolved.toml"),
        "artifact_sha256": {},
    }
    manifest["artifact_sha256"] = {
        name: sha256_file(run_dir / name)
        for name in (
            "config.resolved.toml",
            WARMUPS,
            "requests.jsonl",
            "outputs.jsonl",
            "telemetry.jsonl.gz",
        )
    }
    write_json(run_dir / "manifest.json", manifest)
    return run_dir


def test_a_complete_run_validates(tmp_path: Path) -> None:
    report = validate_run(complete_run(tmp_path))

    assert report.ok is True
    assert report.errors == ()
    assert report.status is RunStatus.COMPLETED
    assert report.record_counts["requests.jsonl"] == 1
    assert report.checksums["requests.jsonl"]


def test_a_missing_raw_artifact_fails_validation(tmp_path: Path) -> None:
    run_dir = complete_run(tmp_path)
    (run_dir / "outputs.jsonl").unlink()

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("outputs.jsonl" in error for error in report.errors)


def test_a_missing_derived_artifact_is_not_an_error(tmp_path: Path) -> None:
    """Reports are derived and can be regenerated without repeating inference."""
    report = validate_run(complete_run(tmp_path))

    assert report.ok is True
    assert any("report.md" in note for note in report.warnings)


def test_an_oversized_artifact_fails_validation(tmp_path: Path) -> None:
    run_dir = complete_run(tmp_path)
    (run_dir / "outputs.jsonl").write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("25" in error and "outputs.jsonl" in error for error in report.errors)


def test_an_interrupted_run_is_preserved_and_reported_as_such(tmp_path: Path) -> None:
    run_dir = complete_run(tmp_path, RunStatus.INTERRUPTED)

    report = validate_run(run_dir)

    assert report.status is RunStatus.INTERRUPTED
    assert report.ok is False
    assert any("interrupted" in note.lower() for note in report.warnings + report.errors)


def test_validation_reports_a_run_directory_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(ResultsError, match="not found"):
        validate_run(tmp_path / "absent")


def test_a_manifest_that_is_not_valid_json_fails_validation(tmp_path: Path) -> None:
    run_dir = complete_run(tmp_path)
    (run_dir / "manifest.json").write_text("{broken", encoding="utf-8")

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("manifest.json" in error for error in report.errors)


def test_the_validation_report_serializes(tmp_path: Path) -> None:
    report = validate_run(complete_run(tmp_path))
    payload = json.loads(json.dumps(report.to_dict()))

    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert "requests.jsonl" in payload["checksums"]


def test_validation_is_idempotent_and_does_not_hash_itself(tmp_path: Path) -> None:
    run_dir = complete_run(tmp_path)
    write_json(run_dir / VALIDATION, validate_run(run_dir).to_dict())
    first = validate_run(run_dir)
    write_json(run_dir / VALIDATION, first.to_dict())
    second = validate_run(run_dir)

    assert first.to_dict() == second.to_dict()
    assert VALIDATION not in second.checksums
    assert VALIDATION not in second.sizes


def test_every_required_raw_artifact_is_checked(tmp_path: Path) -> None:
    for name in REQUIRED_RAW_ARTIFACTS:
        run_dir = complete_run(tmp_path / name.replace(".", "_"))
        (run_dir / name).unlink()
        assert validate_run(run_dir).ok is False, f"{name} must be required"


def test_schema_v1_run_passes_semantic_validation(tmp_path: Path) -> None:
    report = validate_run(schema_v1_run(tmp_path))

    assert report.ok is True
    assert report.errors == ()


def test_schema_v2_run_passes_semantic_validation(tmp_path: Path) -> None:
    report = validate_run(schema_v2_run(tmp_path))

    assert report.ok is True
    assert report.errors == ()


@pytest.mark.parametrize(
    "policy",
    ["uuid_slot_prefix_v2", "uuid_slot_prefix_v3", "uuid_stable_slot_prefix_v4"],
)
def test_schema_v2_accepts_the_slot_prefixed_cache_buster_policy(
    tmp_path: Path, policy: str
) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["cache_buster_policy"] = policy
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is True
    assert report.errors == ()


@pytest.mark.parametrize("schema", [None, 999])
def test_missing_or_unknown_schema_version_fails_closed(tmp_path: Path, schema: int | None) -> None:
    run_dir = complete_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if schema is None:
        manifest.pop("schema_version")
    else:
        manifest["schema_version"] = schema
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("schema_version" in error for error in report.errors)


def test_partial_gpu_offload_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["models"][0]["fully_on_gpu"] = False
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("fully on GPU" in error for error in report.errors)


def test_a_changed_model_digest_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["model_digest"] = "different"
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("digest" in error for error in report.errors)


def test_cached_prompt_tokens_above_the_allowed_excess_fail_validation(
    tmp_path: Path,
) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["prompt_eval_cached_count"] = 22
    outputs[0]["metrics"]["excess_cached_prompt_tokens"] = 2
    outputs[0]["metrics"]["uncached_prompt_tokens"] = 4
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("allowed excess" in error for error in report.errors)


def test_cache_baseline_in_output_must_match_the_manifest(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["metrics"]["template_cache_baseline_tokens"] = 19
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("cache baseline" in error for error in report.errors)


def test_schema_v2_requires_the_declared_template_cache_policy(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("prompt_cache_policy")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("prompt cache policy" in error for error in report.errors)


def test_schema_v2_requires_the_declared_cache_buster_policy(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("cache_buster_policy")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("cache buster policy" in error for error in report.errors)


def test_a_telemetry_gap_above_500_ms_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["metrics"]["max_telemetry_gap_seconds"] = 0.75
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("telemetry gap" in error for error in report.errors)


def test_missing_request_telemetry_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    (run_dir / "telemetry.jsonl.gz").unlink()
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "another-request", "monotonic_s": 0.0})

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("no telemetry" in error for error in report.errors)


def test_schema_v2_rejects_tampered_artifact_hashes(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    with (run_dir / "requests.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"request_id":"r1"}\n')

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("checksum" in error for error in report.errors)


def test_schema_v2_rejects_incomplete_request_counts(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["prompt_count"] = 2
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("expected 2 measured requests" in error for error in report.errors)


def test_schema_v2_requires_exact_frozen_model_digest_coverage(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["controls"]["expected_model_digests"]["unexpected:model"] = "f" * 64
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("frozen model digest coverage" in error for error in report.errors)


def test_schema_v2_rejects_a_warmup_floor_not_supported_by_raw_records(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["models"][0]["template_cache_baseline_tokens"] = 21
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("warm-up" in error and "floor" in error for error in report.errors)


def test_schema_v2_rejects_a_reloaded_cache_floor_warmup(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    warmups = list(read_jsonl(run_dir / WARMUPS))
    warmups[1]["load_duration_ns"] = 3_000_000_000
    (run_dir / WARMUPS).unlink()
    with JsonlWriter(run_dir / WARMUPS) as writer:
        for record in warmups:
            writer.write(record)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_sha256"][WARMUPS] = sha256_file(run_dir / WARMUPS)
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("reloaded during cache-floor warm-up" in error for error in report.errors)


def test_schema_v2_rejects_a_measured_model_reload(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = list(read_jsonl(run_dir / "outputs.jsonl"))
    outputs[0]["load_duration_ns"] = 3_000_000_000
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["outputs.jsonl"] = sha256_file(run_dir / "outputs.jsonl")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("reloaded" in error for error in report.errors)


@pytest.mark.parametrize(
    "field",
    [
        "prompt_eval_count",
        "total_duration_ns",
        "prompt_eval_duration_ns",
        "eval_duration_ns",
        "ttft_s",
    ],
)
def test_schema_v2_rejects_missing_required_runtime_metrics(tmp_path: Path, field: str) -> None:
    run_dir = schema_v2_run(tmp_path)
    outputs = list(read_jsonl(run_dir / "outputs.jsonl"))
    outputs[0][field] = None
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["outputs.jsonl"] = sha256_file(run_dir / "outputs.jsonl")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("required runtime metric" in error for error in report.errors)


def test_schema_v2_rejects_decreasing_raw_telemetry_timestamps(tmp_path: Path) -> None:
    run_dir = schema_v2_run(tmp_path)
    (run_dir / "telemetry.jsonl.gz").unlink()
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "r0", "monotonic_s": 0.1})
        writer.write({"request_id": "r0", "monotonic_s": 0.0})
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["telemetry.jsonl.gz"] = sha256_file(run_dir / "telemetry.jsonl.gz")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("timestamp order" in error for error in report.errors)
