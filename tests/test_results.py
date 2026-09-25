"""Tests for immutable run artifacts: atomic writes, integrity, and privacy."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from llm_energy_bench.results import (
    MAX_ARTIFACT_BYTES,
    REQUIRED_RAW_ARTIFACTS,
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
    write_json(run_dir / "manifest.json", {"run_id": run_dir.name, "status": status.value})
    write_text(run_dir / "config.resolved.toml", '[experiment]\nid = "e"\n')
    with JsonlWriter(run_dir / "requests.jsonl") as writer:
        writer.write({"request_id": "r0", "valid": True})
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write({"request_id": "r0", "text": "hello"})
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "r0", "power_instant_watts": 45.0})
    return run_dir


def schema_v1_run(tmp_path: Path) -> Path:
    run_dir = complete_run(tmp_path)
    digest = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
    write_json(
        run_dir / "manifest.json",
        {
            "schema_version": 1,
            "run_id": run_dir.name,
            "status": "completed",
            "prompt_cache_policy": "template_floor_v1",
            "cache_buster_policy": "uuid_prefix_v1",
            "models": [
                {
                    "name": "llama3.2:3b-instruct-q4_K_M",
                    "digest": digest,
                    "fully_on_gpu": True,
                    "template_cache_baseline_tokens": 20,
                }
            ],
        },
    )
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(
            {
                "request_id": "r0",
                "model": "llama3.2:3b-instruct-q4_K_M",
                "model_digest": digest,
                "valid": True,
                "invalid_reasons": [],
                "prompt_eval_cached_count": 20,
                "metrics": {
                    "gpu_energy_joules": 12.0,
                    "telemetry_sample_count": 2,
                    "max_telemetry_gap_seconds": 0.1,
                    "template_cache_baseline_tokens": 20,
                    "excess_cached_prompt_tokens": 0,
                },
            }
        )
    (run_dir / "telemetry.jsonl.gz").unlink()
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "r0", "monotonic_s": 0.0})
        writer.write({"request_id": "r0", "monotonic_s": 0.1})
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


def test_every_required_raw_artifact_is_checked(tmp_path: Path) -> None:
    for name in REQUIRED_RAW_ARTIFACTS:
        run_dir = complete_run(tmp_path / name.replace(".", "_"))
        (run_dir / name).unlink()
        assert validate_run(run_dir).ok is False, f"{name} must be required"


def test_schema_v1_run_passes_semantic_validation(tmp_path: Path) -> None:
    report = validate_run(schema_v1_run(tmp_path))

    assert report.ok is True
    assert report.errors == ()


def test_partial_gpu_offload_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["models"][0]["fully_on_gpu"] = False
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("fully on GPU" in error for error in report.errors)


def test_a_changed_model_digest_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["model_digest"] = "different"
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("digest" in error for error in report.errors)


def test_cached_prompt_tokens_above_the_template_baseline_fail_validation(
    tmp_path: Path,
) -> None:
    run_dir = schema_v1_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["prompt_eval_cached_count"] = 21
    outputs[0]["metrics"]["excess_cached_prompt_tokens"] = 1
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("template baseline" in error for error in report.errors)


def test_cache_baseline_in_output_must_match_the_manifest(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["metrics"]["template_cache_baseline_tokens"] = 19
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("cache baseline" in error for error in report.errors)


def test_schema_v1_requires_the_declared_template_cache_policy(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("prompt_cache_policy")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("prompt cache policy" in error for error in report.errors)


def test_schema_v1_requires_the_declared_cache_buster_policy(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("cache_buster_policy")
    write_json(run_dir / "manifest.json", manifest)

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("cache buster policy" in error for error in report.errors)


def test_a_telemetry_gap_above_500_ms_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    outputs = read_jsonl(run_dir / "outputs.jsonl")
    outputs[0]["metrics"]["max_telemetry_gap_seconds"] = 0.75
    (run_dir / "outputs.jsonl").unlink()
    with JsonlWriter(run_dir / "outputs.jsonl") as writer:
        writer.write(outputs[0])

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("telemetry gap" in error for error in report.errors)


def test_missing_request_telemetry_fails_semantic_validation(tmp_path: Path) -> None:
    run_dir = schema_v1_run(tmp_path)
    (run_dir / "telemetry.jsonl.gz").unlink()
    with GzipJsonlWriter(run_dir / "telemetry.jsonl.gz") as writer:
        writer.write({"request_id": "another-request", "monotonic_s": 0.0})

    report = validate_run(run_dir)

    assert report.ok is False
    assert any("no telemetry" in error for error in report.errors)
