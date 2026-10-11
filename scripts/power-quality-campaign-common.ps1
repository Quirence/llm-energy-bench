Set-StrictMode -Version Latest

function Assert-OllamaServerVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedVersion,

        [scriptblock]$VersionRequest
    )

    $uri = $BaseUrl.TrimEnd("/") + "/api/version"
    if ($null -eq $VersionRequest) {
        $VersionRequest = {
            param($requestUri)
            $response = Invoke-RestMethod -Uri $requestUri -Method Get -TimeoutSec 10
            [string]$response.version
        }
    }

    try {
        $observedVersion = ([string](& $VersionRequest $uri)).Trim()
    }
    catch {
        throw "Ollama server version query failed at ${uri}: $($_.Exception.Message)"
    }

    if ([string]::IsNullOrWhiteSpace($observedVersion)) {
        throw "Ollama server version query returned an empty version at $uri"
    }
    if ($observedVersion -ne $ExpectedVersion) {
        throw "Ollama server version mismatch: expected $ExpectedVersion, found $observedVersion"
    }
    return $observedVersion
}


function Invoke-OllamaStop {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model,

        [string]$Executable = "ollama"
    )

    # Windows PowerShell 5.1 turns every native stderr line into an error record,
    # and under ErrorActionPreference=Stop that record aborts the caller even when
    # stderr is redirected. Ollama 0.35 writes its spinner to stderr on success, so
    # only the exit code decides whether the stop failed.
    try {
        $command = Get-Command -Name $Executable -CommandType Application -ErrorAction Stop |
            Select-Object -First 1
    }
    catch {
        throw "ollama executable not found: $Executable"
    }

    $previousPreference = $ErrorActionPreference
    $exitCode = $null
    try {
        $ErrorActionPreference = "Continue"
        & $command.Source stop $Model 2>$null | Out-Null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0) {
        throw "ollama stop $Model exited with code $exitCode"
    }
}


function Invoke-CampaignCleanup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Models,

        [Parameter(Mandatory = $true)]
        [double]$DefaultPowerWatts,

        [Parameter(Mandatory = $true)]
        [scriptblock]$StopModelAction,

        [Parameter(Mandatory = $true)]
        [scriptblock]$SetPowerAction,

        [Parameter(Mandatory = $true)]
        [scriptblock]$ReadPowerAction
    )

    $errors = [Collections.Generic.List[string]]::new()
    foreach ($model in $Models) {
        try {
            $null = & $StopModelAction $model
        }
        catch {
            $errors.Add("stop model $model failed: $($_.Exception.Message)")
        }
    }

    try {
        $null = & $SetPowerAction $DefaultPowerWatts
    }
    catch {
        $errors.Add("default power set failed: $($_.Exception.Message)")
    }

    $observedPower = $null
    try {
        $rawPower = & $ReadPowerAction
        $observedPower = [double]::Parse(
            ([string]$rawPower).Trim(),
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    catch {
        $errors.Add("default power readback failed: $($_.Exception.Message)")
    }

    if (
        $null -ne $observedPower -and
        [Math]::Abs($observedPower - $DefaultPowerWatts) -gt 1.0
    ) {
        $errors.Add(
            "default power mismatch: expected $DefaultPowerWatts W, observed $observedPower W"
        )
    }

    return [pscustomobject]@{
        Errors = @($errors)
        ObservedPowerWatts = $observedPower
    }
}


function Assert-CampaignRun {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [object]$Manifest,

        [Parameter(Mandatory = $true)]
        [object]$Validation,

        [Parameter(Mandatory = $true)]
        [string]$DirectoryName,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedHostId,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedHostRole,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedCommit,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedRuntimeVersion,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedPromptFingerprint,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedGpuName,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedDriverVersion,

        [Parameter(Mandatory = $true)]
        [double[]]$ExpectedPowers,

        [Parameter(Mandatory = $true)]
        [hashtable]$ExpectedRunMatrix,

        [Parameter(Mandatory = $true)]
        [hashtable]$SeenRunMatrix,

        [Parameter(Mandatory = $true)]
        [hashtable]$ExpectedDigests
    )

    $modelRecords = @($Manifest.models)
    if ($modelRecords.Count -ne 1) {
        throw "Final validation failed: $DirectoryName"
    }
    $modelRecord = $modelRecords[0]
    $conditionId = [string]$Manifest.study.condition_id
    if ($conditionId -notmatch "-p(?<power>[0-9]+)$") {
        throw "Unexpected condition id: $conditionId"
    }
    $conditionPower = [double]$Matches.power
    $modelName = [string]$modelRecord.model
    $expectedDigest = if ($ExpectedDigests.ContainsKey($modelName)) {
        $ExpectedDigests[$modelName]
    } else {
        $null
    }
    $matrixKey = (
        "$modelName|$([int]$conditionPower)|" +
        "$($Manifest.study.launch_index)|$conditionId"
    )

    if (
        $Manifest.schema_version -ne 3 -or
        $Manifest.status -ne "completed" -or
        $Manifest.host_id -ne $ExpectedHostId -or
        $Manifest.git_commit -ne $ExpectedCommit -or
        $Manifest.completed_requests -ne 60 -or
        $Manifest.valid_requests -ne 60 -or
        $Manifest.runtime.version -ne $ExpectedRuntimeVersion -or
        $Manifest.prompt_set_sha256 -ne $ExpectedPromptFingerprint -or
        $Manifest.study.protocol_id -ne "power-quality-v2" -or
        $Manifest.study.host_role -ne $ExpectedHostRole -or
        $Manifest.study.launch_index -notin @(1, 2, 3) -or
        -not $ExpectedRunMatrix.ContainsKey($matrixKey) -or
        $SeenRunMatrix.ContainsKey($matrixKey) -or
        $conditionPower -notin $ExpectedPowers -or
        $Manifest.gpu.name -ne $ExpectedGpuName -or
        $Manifest.gpu.driver_version -ne $ExpectedDriverVersion -or
        [Math]::Abs([double]$Manifest.gpu.power_limit_watts - $conditionPower) -gt 1.0 -or
        $null -eq $expectedDigest -or
        $modelRecord.digest -ne $expectedDigest -or
        -not $modelRecord.fully_on_gpu -or
        [double]$modelRecord.gpu_fraction -ne 1.0 -or
        -not $Validation.ok
    ) {
        throw "Final validation failed: $DirectoryName"
    }

    $SeenRunMatrix[$matrixKey] = $true
    return [string]$Manifest.run_id
}
