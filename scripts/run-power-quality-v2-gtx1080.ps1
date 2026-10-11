param(
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedTag = "power-quality-v2-gtx1080-code-v2"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$commonScript = Join-Path $PSScriptRoot "power-quality-campaign-common.ps1"
. $commonScript
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runRoot = Join-Path $repoRoot "experiments\runs\power-quality-v2"
$dependencyLock = Join-Path $repoRoot "requirements\power-quality-v2-windows-py312.lock"
$expectedDependencyLockSha256 = "474a00ce6ca43b0ee2a411dcd71f79a95ef7a94d7ffe699cfb1becc80c4662c0"
$defaultPowerWatts = 200
$expectedRuntimeVersion = "0.35.0"
$expectedHostId = "gtx1080-observation"
$expectedHostRole = "external"
$expectedGpuName = "NVIDIA GeForce GTX 1080"
$expectedDriverVersion = "582.66"
$expectedVramMiB = 8192
$expectedMinimumPowerWatts = 90
$expectedMaximumPowerWatts = 240
$expectedPowers = @(100.0, 150.0, 200.0)
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
$expectedPackages = @{
    "anyio" = "4.15.1"
    "certifi" = "2026.7.22"
    "colorama" = "0.4.6"
    "h11" = "0.16.0"
    "hatchling" = "1.32.4"
    "httpcore" = "1.0.9"
    "httpx" = "0.28.1"
    "idna" = "3.20"
    "iniconfig" = "2.3.1"
    "llm-energy-bench" = "0.1.0"
    "nvidia-ml-py" = "13.615.71"
    "packaging" = "26.3"
    "pathspec" = "1.1.1"
    "pluggy" = "1.6.0"
    "pygments" = "2.21.0"
    "pytest" = "9.1.1"
    "ruff" = "0.16.9"
    "tomlkit" = "0.15.1"
    "trove-classifiers" = "2026.9.21.13"
    "typing-extensions" = "4.16.0"
}

# Frozen before measurement: power position varies across launch blocks and
# model-first order is near-balanced across the external schedule.
$schedule = @(
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch1.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch1.toml" },
    [pscustomobject]@{ Power = 200; Config = "qwen3-q4-p200-launch1.toml" },
    [pscustomobject]@{ Power = 200; Config = "llama32-q4-p200-launch1.toml" },
    [pscustomobject]@{ Power = 150; Config = "llama32-q4-p150-launch1.toml" },
    [pscustomobject]@{ Power = 150; Config = "qwen3-q4-p150-launch1.toml" },

    [pscustomobject]@{ Power = 150; Config = "qwen3-q4-p150-launch2.toml" },
    [pscustomobject]@{ Power = 150; Config = "llama32-q4-p150-launch2.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch2.toml" },
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch2.toml" },
    [pscustomobject]@{ Power = 200; Config = "llama32-q4-p200-launch2.toml" },
    [pscustomobject]@{ Power = 200; Config = "qwen3-q4-p200-launch2.toml" },

    [pscustomobject]@{ Power = 200; Config = "llama32-q4-p200-launch3.toml" },
    [pscustomobject]@{ Power = 200; Config = "qwen3-q4-p200-launch3.toml" },
    [pscustomobject]@{ Power = 150; Config = "qwen3-q4-p150-launch3.toml" },
    [pscustomobject]@{ Power = 150; Config = "llama32-q4-p150-launch3.toml" },
    [pscustomobject]@{ Power = 100; Config = "llama32-q4-p100-launch3.toml" },
    [pscustomobject]@{ Power = 100; Config = "qwen3-q4-p100-launch3.toml" }
)

$expectedRunMatrix = @{}
foreach ($item in $schedule) {
    $stem = [IO.Path]::GetFileNameWithoutExtension($item.Config)
    if ($stem -notmatch "^(?<slug>llama32-q4|qwen3-q4)-p(?<power>[0-9]+)-launch(?<launch>[123])$") {
        throw "Invalid frozen schedule entry: $($item.Config)"
    }
    $scheduledModel = if ($Matches.slug -eq "llama32-q4") {
        "llama3.2:3b-instruct-q4_K_M"
    } else {
        "qwen3:4b-instruct-2507-q4_K_M"
    }
    $scheduledCondition = "$($Matches.slug)-p$($Matches.power)"
    $matrixKey = "$scheduledModel|$($Matches.power)|$($Matches.launch)|$scheduledCondition"
    if ($expectedRunMatrix.ContainsKey($matrixKey)) {
        throw "Duplicate frozen schedule entry: $matrixKey"
    }
    $expectedRunMatrix[$matrixKey] = $true
}
if ($expectedRunMatrix.Count -ne 18) {
    throw "Frozen schedule must contain exactly 18 unique conditions"
}

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

Write-Host "Frozen Palit GTX 1080 GameRock schedule:"
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

$dependencyLockSha256 = (Get-FileHash $dependencyLock -Algorithm SHA256).Hash.ToLowerInvariant()
if ($dependencyLockSha256 -ne $expectedDependencyLockSha256) {
    throw "Dependency lock hash mismatch: $dependencyLockSha256"
}
$pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
Assert-LastExitCode "Python version check"
if ($pythonVersion -notmatch "^Python 3\.12\.") {
    throw "CPython 3.12 x86-64 is required; found: $pythonVersion"
}
$pythonArchitecture = (& $python -c "import platform; print(platform.machine())").Trim()
Assert-LastExitCode "Python architecture check"
if ($pythonArchitecture -notin @("AMD64", "x86_64")) {
    throw "CPython 3.12 x86-64 is required; architecture is $pythonArchitecture"
}
$packageRecords = & $python -m pip list --format=json | ConvertFrom-Json
Assert-LastExitCode "Python package inventory"
$installedPackages = @{}
foreach ($package in $packageRecords) {
    $packageName = ([string]$package.name).ToLowerInvariant().Replace("_", "-")
    $installedPackages[$packageName] = [string]$package.version
}
$dependencySnapshot = [ordered]@{}
foreach ($packageName in @($expectedPackages.Keys | Sort-Object)) {
    if (
        -not $installedPackages.ContainsKey($packageName) -or
        $installedPackages[$packageName] -ne $expectedPackages[$packageName]
    ) {
        $observedVersion = $installedPackages[$packageName]
        throw (
            "Python package mismatch for ${packageName}: " +
            "expected $($expectedPackages[$packageName]), found $observedVersion"
        )
    }
    $dependencySnapshot[$packageName] = $installedPackages[$packageName]
}
$pipVersion = $installedPackages["pip"]

$ollamaServerVersion = Assert-OllamaServerVersion `
    -BaseUrl "http://127.0.0.1:11434" `
    -ExpectedVersion $expectedRuntimeVersion

$gpuRow = & nvidia-smi -i 0 `
    --query-gpu=name,driver_version,memory.total,power.default_limit,power.min_limit,power.max_limit `
    --format=csv,noheader,nounits
Assert-LastExitCode "Frozen GPU profile check"
$gpuParts = @($gpuRow -split "," | ForEach-Object { $_.Trim() })
if (
    $gpuParts.Count -ne 6 -or
    $gpuParts[0] -ne $expectedGpuName -or
    $gpuParts[1] -ne $expectedDriverVersion -or
    [double]$gpuParts[2] -ne $expectedVramMiB -or
    [double]$gpuParts[3] -ne $defaultPowerWatts -or
    [double]$gpuParts[4] -ne $expectedMinimumPowerWatts -or
    [double]$gpuParts[5] -ne $expectedMaximumPowerWatts
) {
    throw "GPU or driver differs from the frozen profile: $gpuRow"
}

$beforeRunDirs = @{}
if (Test-Path $runRoot) {
    Get-ChildItem $runRoot -Directory | ForEach-Object { $beforeRunDirs[$_.FullName] = $true }
}

$seriesError = $null
try {
    foreach ($item in $schedule) {
        $config = Join-Path $repoRoot ("configs\power-quality-v2\gtx1080\" + $item.Config)
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
catch {
    $seriesError = $_
}
finally {
    Write-Host "Restoring default power limit $defaultPowerWatts W"
    $cleanup = Invoke-CampaignCleanup `
        -Models $models `
        -DefaultPowerWatts $defaultPowerWatts `
        -StopModelAction {
            param($model)
            & ollama stop $model 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "ollama stop exited with code $LASTEXITCODE"
            }
        } `
        -SetPowerAction {
            param($watts)
            & nvidia-smi -i 0 -pl $watts | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "nvidia-smi -pl exited with code $LASTEXITCODE"
            }
        } `
        -ReadPowerAction {
            $row = & nvidia-smi -i 0 `
                --query-gpu=power.limit --format=csv,noheader,nounits
            if ($LASTEXITCODE -ne 0) {
                throw "nvidia-smi readback exited with code $LASTEXITCODE"
            }
            ([string]$row).Trim()
        }
    if ($cleanup.Errors.Count -ne 0) {
        $cleanupMessage = $cleanup.Errors -join "; "
        if ($null -ne $seriesError) {
            throw "campaign failed: $($seriesError.Exception.Message); cleanup failed: $cleanupMessage"
        }
        throw "campaign cleanup failed: $cleanupMessage"
    }
    Write-Host "Verified restored power limit: $($cleanup.ObservedPowerWatts) W"
}

if ($null -ne $seriesError) {
    throw $seriesError
}

$newRunDirs = @(
    Get-ChildItem $runRoot -Directory |
        Where-Object { -not $beforeRunDirs.ContainsKey($_.FullName) } |
        Sort-Object Name
)
if ($newRunDirs.Count -ne 18) {
    throw "Expected 18 new run directories; found $($newRunDirs.Count)"
}

$runIds = @()
$seenRunMatrix = @{}
foreach ($directory in $newRunDirs) {
    $manifest = Get-Content (Join-Path $directory.FullName "manifest.json") -Raw |
        ConvertFrom-Json
    $validation = Get-Content (Join-Path $directory.FullName "validation.json") -Raw |
        ConvertFrom-Json
    $runIds += Assert-CampaignRun `
        -Manifest $manifest `
        -Validation $validation `
        -DirectoryName $directory.Name `
        -ExpectedHostId $expectedHostId `
        -ExpectedHostRole $expectedHostRole `
        -ExpectedCommit $commit `
        -ExpectedRuntimeVersion $expectedRuntimeVersion `
        -ExpectedPromptFingerprint $expectedPromptFingerprint `
        -ExpectedGpuName $expectedGpuName `
        -ExpectedDriverVersion $expectedDriverVersion `
        -ExpectedPowers $expectedPowers `
        -ExpectedRunMatrix $expectedRunMatrix `
        -SeenRunMatrix $seenRunMatrix `
        -ExpectedDigests $expectedDigests
}
if ($seenRunMatrix.Count -ne $expectedRunMatrix.Count) {
    throw "Expected exact 18-condition matrix; found $($seenRunMatrix.Count)"
}

$receipt = [ordered]@{
    schema_version = 1
    protocol_id = "power-quality-v2"
    host_id = "gtx1080-observation"
    code_tag = $expectedTag
    git_commit = $commit
    python_version = $pythonVersion
    python_architecture = $pythonArchitecture
    dependency_lock_sha256 = $dependencyLockSha256
    pip_version = $pipVersion
    dependency_versions = $dependencySnapshot
    runtime_version = $ollamaServerVersion
    driver_version_expected = $expectedDriverVersion
    power_levels_watts = @(100, 150, 200)
    run_count = $runIds.Count
    run_ids = $runIds
    validation = "18/18 completed; 1080/1080 measured requests valid"
    default_power_restored_watts = $defaultPowerWatts
}
$receiptPath = Join-Path $runRoot "gtx1080-campaign-receipt.json"
$receipt | ConvertTo-Json -Depth 4 | Set-Content $receiptPath -Encoding utf8

Write-Host "Series accepted locally: 18/18 runs, 1080/1080 valid requests."
Write-Host "Default 200 W limit restored. Receipt: $receiptPath"
Write-Host "Now follow the upload section in docs/dimas-gtx1080-task.md."
