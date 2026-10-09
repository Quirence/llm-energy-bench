param(
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedTag = "power-quality-v2-rtx4060ti-code"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runRoot = Join-Path $repoRoot "experiments\runs\power-quality-v2"
$defaultPowerWatts = 160
$coolTemperatureC = 50
$maxIdleVramMiB = 2048
$maxWaitMinutes = 20
$models = @(
    "llama3.2:3b-instruct-q4_K_M",
    "qwen3:4b-instruct-2507-q4_K_M"
)
$expectedDigests = @{
    "llama3.2:3b-instruct-q4_K_M" = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
    "qwen3:4b-instruct-2507-q4_K_M" = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
}
$expectedPromptFingerprint = "7d7d1ee71cacc1129d4076b18d5ceb630052950994acab18e112892194d099ff"

# Frozen before measurement: power position varies across launch blocks and
# model-first order is balanced within each block.
$schedule = @(
    [pscustomobject]@{ Power = 160; Config = "llama32-q4-p160-launch1.toml" },
    [pscustomobject]@{ Power = 160; Config = "qwen3-q4-p160-launch1.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch1.toml" },
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch1.toml" },
    [pscustomobject]@{ Power = 195; Config = "llama32-q4-p195-launch1.toml" },
    [pscustomobject]@{ Power = 195; Config = "qwen3-q4-p195-launch1.toml" },
    [pscustomobject]@{ Power = 130; Config = "qwen3-q4-p130-launch1.toml" },
    [pscustomobject]@{ Power = 130; Config = "llama32-q4-p130-launch1.toml" },

    [pscustomobject]@{ Power = 130; Config = "qwen3-q4-p130-launch2.toml" },
    [pscustomobject]@{ Power = 130; Config = "llama32-q4-p130-launch2.toml" },
    [pscustomobject]@{ Power = 195; Config = "llama32-q4-p195-launch2.toml" },
    [pscustomobject]@{ Power = 195; Config = "qwen3-q4-p195-launch2.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch2.toml" },
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch2.toml" },
    [pscustomobject]@{ Power = 160; Config = "llama32-q4-p160-launch2.toml" },
    [pscustomobject]@{ Power = 160; Config = "qwen3-q4-p160-launch2.toml" },

    [pscustomobject]@{ Power = 195; Config = "llama32-q4-p195-launch3.toml" },
    [pscustomobject]@{ Power = 195; Config = "qwen3-q4-p195-launch3.toml" },
    [pscustomobject]@{ Power = 160; Config = "qwen3-q4-p160-launch3.toml" },
    [pscustomobject]@{ Power = 160; Config = "llama32-q4-p160-launch3.toml" },
    [pscustomobject]@{ Power = 130; Config = "llama32-q4-p130-launch3.toml" },
    [pscustomobject]@{ Power = 130; Config = "qwen3-q4-p130-launch3.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch3.toml" },
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch3.toml" }
)

function Assert-LastExitCode {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action exited with code $LASTEXITCODE"
    }
}

function Stop-StudyModels {
    foreach ($model in $models) {
        & ollama stop $model 2>$null | Out-Null
    }
}

function Wait-GpuReady {
    param([int]$ExpectedPowerWatts)

    $deadline = (Get-Date).AddMinutes($maxWaitMinutes)
    while ($true) {
        $row = & nvidia-smi -i 0 `
            --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.limit `
            --format=csv,noheader,nounits
        Assert-LastExitCode "GPU state query"
        $parts = @($row -split "," | ForEach-Object { $_.Trim() })
        if ($parts.Count -ne 4) {
            throw "Unexpected nvidia-smi response: $row"
        }
        $temperature = [double]::Parse(
            $parts[0], [Globalization.CultureInfo]::InvariantCulture
        )
        $utilization = [double]::Parse(
            $parts[1], [Globalization.CultureInfo]::InvariantCulture
        )
        $vram = [double]::Parse($parts[2], [Globalization.CultureInfo]::InvariantCulture)
        $power = [double]::Parse($parts[3], [Globalization.CultureInfo]::InvariantCulture)
        $powerMatches = [Math]::Abs($power - $ExpectedPowerWatts) -le 1.0
        if (
            $temperature -le $coolTemperatureC -and
            $utilization -le 5.0 -and
            $vram -le $maxIdleVramMiB -and
            $powerMatches
        ) {
            Write-Host (
                "GPU ready: {0} C, {1}% load, {2} MiB VRAM, {3} W" -f `
                    $temperature, $utilization, $vram, $power
            )
            return
        }
        if ((Get-Date) -ge $deadline) {
            throw (
                "GPU did not become ready in $maxWaitMinutes minutes: " +
                "$temperature C, $utilization% load, $vram MiB VRAM, $power W"
            )
        }
        Write-Host (
            "Waiting for GPU: {0} C, {1}% load, {2} MiB VRAM, {3} W" -f `
                $temperature, $utilization, $vram, $power
        )
        Start-Sleep -Seconds 20
    }
}

Set-Location $repoRoot

Write-Host "Frozen RTX 4060 Ti schedule:"
for ($index = 0; $index -lt $schedule.Count; $index++) {
    Write-Host ("{0,2}. {1,3} W  {2}" -f ($index + 1), $schedule[$index].Power, $schedule[$index].Config)
}

if (-not $Execute) {
    Write-Host "Plan only. Run with -Execute from an Administrator PowerShell."
    exit 0
}

foreach ($command in @("git", "ollama", "nvidia-smi")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Command not found: $command"
    }
}
if (-not (Test-Path $python)) {
    throw "Python 3.12 environment not found: $python"
}

$tags = @(& git tag --points-at HEAD)
Assert-LastExitCode "Git tag check"
if ($tags -notcontains $expectedTag) {
    throw "HEAD must have immutable tag $expectedTag"
}
$dirty = @(& git status --porcelain --untracked-files=normal)
Assert-LastExitCode "Git working tree check"
if ($dirty.Count -ne 0) {
    throw "Working tree must be clean before the series: $($dirty -join '; ')"
}
$commit = (& git rev-parse HEAD).Trim()
Assert-LastExitCode "Git commit read"

$ollamaVersion = (& ollama --version 2>&1 | Out-String).Trim()
Assert-LastExitCode "Ollama version check"
if ($ollamaVersion -notmatch "(?<![0-9])0\.35\.0(?![0-9])") {
    throw "Ollama 0.35.0 is required; found: $ollamaVersion"
}

$gpuRow = & nvidia-smi -i 0 `
    --query-gpu=name,driver_version,memory.total,power.default_limit,power.min_limit,power.max_limit `
    --format=csv,noheader,nounits
Assert-LastExitCode "Frozen GPU profile check"
$gpuParts = @($gpuRow -split "," | ForEach-Object { $_.Trim() })
if (
    $gpuParts.Count -ne 6 -or
    $gpuParts[0] -ne "NVIDIA GeForce RTX 4060 Ti" -or
    $gpuParts[1] -ne "560.94" -or
    [double]$gpuParts[2] -ne 8188 -or
    [double]$gpuParts[3] -ne 160 -or
    [double]$gpuParts[4] -ne 100 -or
    [double]$gpuParts[5] -ne 195
) {
    throw "GPU or driver differs from the frozen profile: $gpuRow"
}

$beforeRunDirs = @{}
if (Test-Path $runRoot) {
    Get-ChildItem $runRoot -Directory | ForEach-Object { $beforeRunDirs[$_.FullName] = $true }
}

$restored = $false
try {
    foreach ($item in $schedule) {
        $config = Join-Path $repoRoot ("configs\power-quality-v2\rtx4060ti\" + $item.Config)
        Write-Host "=== $($item.Power) W | $($item.Config) ==="
        & nvidia-smi -i 0 -pl $item.Power
        Assert-LastExitCode "Set power limit to $($item.Power) W"

        Stop-StudyModels
        Wait-GpuReady -ExpectedPowerWatts $item.Power
        & $python -m llm_energy_bench doctor --config $config --json
        Assert-LastExitCode "doctor for $($item.Config)"

        Stop-StudyModels
        Wait-GpuReady -ExpectedPowerWatts $item.Power
        & $python -m llm_energy_bench run --config $config
        Assert-LastExitCode "run for $($item.Config)"
    }
}
finally {
    Write-Host "Restoring default power limit $defaultPowerWatts W"
    & nvidia-smi -i 0 -pl $defaultPowerWatts
    if ($LASTEXITCODE -eq 0) {
        $restored = $true
    }
}

if (-not $restored) {
    throw "Series ended, but default power limit $defaultPowerWatts W was not restored"
}

$newRunDirs = @(
    Get-ChildItem $runRoot -Directory |
        Where-Object { -not $beforeRunDirs.ContainsKey($_.FullName) } |
        Sort-Object Name
)
if ($newRunDirs.Count -ne 24) {
    throw "Expected 24 new run directories; found $($newRunDirs.Count)"
}

$runIds = @()
$seenConditions = @{}
foreach ($directory in $newRunDirs) {
    $manifest = Get-Content (Join-Path $directory.FullName "manifest.json") -Raw |
        ConvertFrom-Json
    $validation = Get-Content (Join-Path $directory.FullName "validation.json") -Raw |
        ConvertFrom-Json
    $modelRecords = @($manifest.models)
    $conditionKey = "$($manifest.study.condition_id)|$($manifest.study.launch_index)"
    if ($manifest.study.condition_id -notmatch "-p(?<power>[0-9]+)$") {
        throw "Unexpected condition id: $($manifest.study.condition_id)"
    }
    $conditionPower = [double]$Matches.power
    $modelRecord = if ($modelRecords.Count -eq 1) { $modelRecords[0] } else { $null }
    $expectedDigest = if ($null -ne $modelRecord) {
        $expectedDigests[[string]$modelRecord.model]
    } else {
        $null
    }
    if (
        $manifest.schema_version -ne 3 -or
        $manifest.status -ne "completed" -or
        $manifest.host_id -ne "rtx4060ti-desktop" -or
        $manifest.git_commit -ne $commit -or
        $manifest.completed_requests -ne 60 -or
        $manifest.valid_requests -ne 60 -or
        $manifest.runtime.version -ne "0.35.0" -or
        $manifest.prompt_set_sha256 -ne $expectedPromptFingerprint -or
        $manifest.study.protocol_id -ne "power-quality-v2" -or
        $manifest.study.host_role -ne "primary" -or
        $manifest.study.launch_index -notin @(1, 2, 3) -or
        $seenConditions.ContainsKey($conditionKey) -or
        $conditionPower -notin @(100.0, 130.0, 160.0, 195.0) -or
        $manifest.gpu.name -ne "NVIDIA GeForce RTX 4060 Ti" -or
        $manifest.gpu.driver_version -ne "560.94" -or
        [Math]::Abs([double]$manifest.gpu.power_limit_watts - $conditionPower) -gt 1.0 -or
        $null -eq $modelRecord -or
        $null -eq $expectedDigest -or
        $modelRecord.digest -ne $expectedDigest -or
        -not $modelRecord.fully_on_gpu -or
        [double]$modelRecord.gpu_fraction -ne 1.0 -or
        -not $validation.ok
    ) {
        throw "Final validation failed: $($directory.Name)"
    }
    $seenConditions[$conditionKey] = $true
    $runIds += $manifest.run_id
}
if ($seenConditions.Count -ne 24) {
    throw "Expected 24 unique study conditions; found $($seenConditions.Count)"
}

$receipt = [ordered]@{
    schema_version = 1
    protocol_id = "power-quality-v2"
    host_id = "rtx4060ti-desktop"
    code_tag = $expectedTag
    git_commit = $commit
    runtime_version = "0.35.0"
    driver_version_expected = "560.94"
    power_levels_watts = @(100, 130, 160, 195)
    run_count = $runIds.Count
    run_ids = $runIds
    validation = "24/24 completed; 1440/1440 measured requests valid"
    default_power_restored_watts = $defaultPowerWatts
}
$receiptPath = Join-Path $runRoot "rtx4060ti-campaign-receipt.json"
$receipt | ConvertTo-Json -Depth 4 | Set-Content $receiptPath -Encoding utf8

Write-Host "Series accepted locally: 24/24 runs, 1440/1440 valid requests."
Write-Host "Default 160 W limit restored. Receipt: $receiptPath"
Write-Host "Now follow the upload section in docs/lev-rtx4060ti-task.md."
