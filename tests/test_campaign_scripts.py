from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_SCRIPT = REPO_ROOT / "scripts" / "power-quality-campaign-common.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
CAMPAIGN_SCRIPTS = (
    REPO_ROOT / "scripts" / "run-power-quality-v2-gtx1080.ps1",
    REPO_ROOT / "scripts" / "run-power-quality-v2-rtx4060ti.ps1",
)


def _ps_quote(path: Path) -> str:
    return str(path).replace("'", "''")


def _run_powershell(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    script = tmp_path / "campaign-test.ps1"
    script.write_text(
        f"$ErrorActionPreference = 'Stop'\n. '{_ps_quote(COMMON_SCRIPT)}'\n{body}\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
def test_cleanup_attempts_every_action_and_preserves_all_failures(tmp_path: Path) -> None:
    result = _run_powershell(
        tmp_path,
        r"""
$script:calls = [Collections.Generic.List[string]]::new()
$params = @{
    Models = @("model-a", "model-b")
    DefaultPowerWatts = 200
    StopModelAction = {
        param($model)
        $script:calls.Add("stop:$model")
        if ($model -eq "model-a") { throw "unload failed" }
    }
    SetPowerAction = {
        param($watts)
        $script:calls.Add("set:$watts")
        throw "set failed"
    }
    ReadPowerAction = {
        $script:calls.Add("read")
        175.0
    }
}
$cleanup = Invoke-CampaignCleanup @params
[pscustomobject]@{
    calls = @($script:calls)
    errors = @($cleanup.Errors)
    observed = $cleanup.ObservedPowerWatts
} | ConvertTo-Json -Compress
""",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["calls"] == ["stop:model-a", "stop:model-b", "set:200", "read"]
    assert payload["observed"] == 175.0
    assert len(payload["errors"]) == 3
    assert any("model-a" in item and "unload failed" in item for item in payload["errors"])
    assert any("set failed" in item for item in payload["errors"])
    assert any("expected 200" in item and "observed 175" in item for item in payload["errors"])


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
@pytest.mark.parametrize(
    ("observed", "failure"),
    [
        ("0.34.2", "expected 0.35.0, found 0.34.2"),
        ("offline", "Ollama server version query failed"),
    ],
)
def test_server_version_guard_rejects_old_or_unavailable_server(
    tmp_path: Path,
    observed: str,
    failure: str,
) -> None:
    request = (
        '{ param($uri) throw "connection refused" }'
        if observed == "offline"
        else f'{{ param($uri) "{observed}" }}'
    )
    result = _run_powershell(
        tmp_path,
        f"""
$params = @{{
    BaseUrl = "http://127.0.0.1:11434"
    ExpectedVersion = "0.35.0"
    VersionRequest = {request}
}}
Assert-OllamaServerVersion @params
""",
    )

    assert result.returncode != 0
    assert failure in (result.stdout + result.stderr)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
def test_manifest_acceptance_uses_the_supplied_gtx1080_driver(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 3,
        "status": "completed",
        "host_id": "gtx1080-observation",
        "git_commit": "abc123",
        "completed_requests": 60,
        "valid_requests": 60,
        "runtime": {"version": "0.35.0"},
        "prompt_set_sha256": "prompt-hash",
        "study": {
            "protocol_id": "power-quality-v2",
            "host_role": "external",
            "launch_index": 1,
            "condition_id": "llama32-q4-p100",
        },
        "gpu": {
            "name": "NVIDIA GeForce GTX 1080",
            "driver_version": "582.66",
            "power_limit_watts": 100.0,
        },
        "models": [
            {
                "model": "llama3.2:3b-instruct-q4_K_M",
                "digest": "digest-a",
                "fully_on_gpu": True,
                "gpu_fraction": 1.0,
            }
        ],
        "run_id": "gtx1080-run-1",
    }
    manifest_json = json.dumps(manifest, separators=(",", ":")).replace("'", "''")
    result = _run_powershell(
        tmp_path,
        f"""
$manifest = '{manifest_json}' | ConvertFrom-Json
$validation = [pscustomobject]@{{ ok = $true }}
$matrix = @{{ "llama3.2:3b-instruct-q4_K_M|100|1|llama32-q4-p100" = $true }}
$seen = @{{}}
$digests = @{{ "llama3.2:3b-instruct-q4_K_M" = "digest-a" }}
$params = @{{
    Manifest = $manifest
    Validation = $validation
    DirectoryName = "run-dir"
    ExpectedHostId = "gtx1080-observation"
    ExpectedHostRole = "external"
    ExpectedCommit = "abc123"
    ExpectedRuntimeVersion = "0.35.0"
    ExpectedPromptFingerprint = "prompt-hash"
    ExpectedGpuName = "NVIDIA GeForce GTX 1080"
    ExpectedDriverVersion = "582.66"
    ExpectedPowers = @(100.0, 150.0, 200.0)
    ExpectedRunMatrix = $matrix
    SeenRunMatrix = $seen
    ExpectedDigests = $digests
}}
$runId = Assert-CampaignRun @params
[pscustomobject]@{{ run_id = $runId; seen = $seen.Count }} | ConvertTo-Json -Compress
""",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == {"run_id": "gtx1080-run-1", "seen": 1}


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
@pytest.mark.parametrize(
    ("actual_host", "seen_entry"),
    [
        ("wrong-host", "$seen = @{}"),
        (
            "gtx1080-observation",
            '$seen = @{ "llama3.2:3b-instruct-q4_K_M|100|1|llama32-q4-p100" = $true }',
        ),
    ],
)
def test_manifest_acceptance_rejects_wrong_host_or_duplicate(
    tmp_path: Path,
    actual_host: str,
    seen_entry: str,
) -> None:
    result = _run_powershell(
        tmp_path,
        f"""
$manifest = [pscustomobject]@{{
    schema_version = 3
    status = "completed"
    host_id = "{actual_host}"
    git_commit = "abc123"
    completed_requests = 60
    valid_requests = 60
    runtime = [pscustomobject]@{{ version = "0.35.0" }}
    prompt_set_sha256 = "prompt-hash"
    study = [pscustomobject]@{{
        protocol_id = "power-quality-v2"
        host_role = "external"
        launch_index = 1
        condition_id = "llama32-q4-p100"
    }}
    gpu = [pscustomobject]@{{
        name = "NVIDIA GeForce GTX 1080"
        driver_version = "582.66"
        power_limit_watts = 100.0
    }}
    models = @([pscustomobject]@{{
        model = "llama3.2:3b-instruct-q4_K_M"
        digest = "digest-a"
        fully_on_gpu = $true
        gpu_fraction = 1.0
    }})
    run_id = "gtx1080-run-1"
}}
$validation = [pscustomobject]@{{ ok = $true }}
$matrix = @{{ "llama3.2:3b-instruct-q4_K_M|100|1|llama32-q4-p100" = $true }}
{seen_entry}
$digests = @{{ "llama3.2:3b-instruct-q4_K_M" = "digest-a" }}
$params = @{{
    Manifest = $manifest
    Validation = $validation
    DirectoryName = "run-dir"
    ExpectedHostId = "gtx1080-observation"
    ExpectedHostRole = "external"
    ExpectedCommit = "abc123"
    ExpectedRuntimeVersion = "0.35.0"
    ExpectedPromptFingerprint = "prompt-hash"
    ExpectedGpuName = "NVIDIA GeForce GTX 1080"
    ExpectedDriverVersion = "582.66"
    ExpectedPowers = @(100.0, 150.0, 200.0)
    ExpectedRunMatrix = $matrix
    SeenRunMatrix = $seen
    ExpectedDigests = $digests
}}
Assert-CampaignRun @params
""",
    )

    assert result.returncode != 0
    assert "Final validation failed: run-dir" in (result.stdout + result.stderr)


def _fake_ollama(tmp_path: Path, exit_code: int) -> Path:
    """A real executable that mimics Ollama 0.35: spinner on stderr, then exit."""
    if os.name == "nt":
        fake = tmp_path / "fake-ollama.cmd"
        fake.write_text(
            "@echo off\r\n"
            ">&2 echo [?25l spinner\r\n"
            '>"%~dp0args.txt" echo %*\r\n'
            f"exit /b {exit_code}\r\n",
            encoding="ascii",
            newline="",
        )
    else:
        fake = tmp_path / "fake-ollama"
        fake.write_text(
            "#!/bin/sh\n"
            'echo "[?25l spinner" >&2\n'
            'echo "$*" > "$(dirname "$0")/args.txt"\n'
            f"exit {exit_code}\n",
            encoding="ascii",
            newline="",
        )
        fake.chmod(0o755)
    return fake


def _invoke_ollama_stop(tmp_path: Path, executable: Path) -> dict[str, str | None]:
    result = _run_powershell(
        tmp_path,
        f"""
$caught = $null
try {{
    Invoke-OllamaStop -Model "model-a" -Executable '{_ps_quote(executable)}'
}}
catch {{
    $caught = $_.Exception.Message
}}
[pscustomobject]@{{
    caught = $caught
    preference = "$ErrorActionPreference"
}} | ConvertTo-Json -Compress
""",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
def test_ollama_stop_accepts_stderr_output_with_a_zero_exit_code(tmp_path: Path) -> None:
    payload = _invoke_ollama_stop(tmp_path, _fake_ollama(tmp_path, 0))

    assert payload["caught"] is None
    assert payload["preference"] == "Stop"
    assert (tmp_path / "args.txt").read_text(encoding="ascii").strip() == "stop model-a"


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
def test_ollama_stop_fails_only_on_a_nonzero_exit_code(tmp_path: Path) -> None:
    payload = _invoke_ollama_stop(tmp_path, _fake_ollama(tmp_path, 3))

    assert payload["caught"] == "ollama stop model-a exited with code 3"
    assert payload["preference"] == "Stop"


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for campaign script tests")
def test_ollama_stop_rejects_a_missing_executable(tmp_path: Path) -> None:
    payload = _invoke_ollama_stop(tmp_path, tmp_path / "missing-ollama.exe")

    assert payload["caught"] is not None
    assert payload["caught"].startswith("ollama executable not found:")
    assert payload["preference"] == "Stop"


@pytest.mark.parametrize("script", CAMPAIGN_SCRIPTS, ids=lambda path: path.stem)
def test_campaign_scripts_stop_models_only_through_the_shared_helper(script: Path) -> None:
    text = script.read_text(encoding="utf-8")

    assert "& ollama stop" not in text
    assert text.count("Invoke-OllamaStop -Model $model") == 2
