param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [string]$ConfigFile
)

$ErrorActionPreference = "Stop"

$AgentRoot = Join-Path $env:ProgramData "KhanCloud\Agent"
$Runtime = Join-Path $AgentRoot "runtime"
$State = $AgentRoot
$Credentials = Join-Path $State "credentials.json"
$Identity = Join-Path $State "identity.json"
$InstalledConfig = Join-Path $State "config.yaml"
$ServiceName = "KhanCloudAgent"

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $env:TEMP "khan-cloud-agent-update-$Timestamp"

Write-Host "===== KHAN CLOUD WINDOWS RUNTIME UPDATE ====="

Write-Host "===== PRE-FLIGHT ====="

if (-not (Test-Path $Credentials -PathType Leaf)) {
    throw "Existing node credentials are missing: $Credentials"
}

if (-not (Test-Path $Identity -PathType Leaf)) {
    throw "Existing node identity is missing: $Identity"
}

if (-not (Test-Path (Join-Path $SourceDir "khan_agent") -PathType Container)) {
    throw "Invalid agent source directory: $SourceDir"
}

if (-not (Test-Path $ConfigFile -PathType Leaf)) {
    throw "Update configuration is missing: $ConfigFile"
}

$Python = Join-Path $Runtime ".venv\Scripts\python.exe"

if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Existing agent Python environment is unavailable: $Python"
}

foreach ($Component in @("khan_agent", "deploy", "tests")) {
    $ComponentPath = Join-Path $SourceDir $Component

    if (-not (Test-Path $ComponentPath -PathType Container)) {
        throw "Update payload missing required component: $Component"
    }
}

Write-Host "===== BACKUP ====="

New-Item -ItemType Directory -Path $Backup -Force | Out-Null

foreach ($Item in @(
    "khan_agent",
    "deploy",
    "tests"
)) {
    $Existing = Join-Path $Runtime $Item

    if (Test-Path $Existing) {
        Copy-Item `
            -Path $Existing `
            -Destination $Backup `
            -Recurse `
            -Force
    }
}

Copy-Item $Credentials (Join-Path $Backup "credentials.json") -Force
Copy-Item $Identity (Join-Path $Backup "identity.json") -Force

if (Test-Path $InstalledConfig) {
    Copy-Item $InstalledConfig (Join-Path $Backup "config.yaml") -Force
}

Write-Host "===== STOP AGENT ====="

$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($Service -and $Service.Status -ne "Stopped") {
    Stop-Service -Name $ServiceName -Force
    (Get-Service -Name $ServiceName).WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Stopped,
        [TimeSpan]::FromSeconds(30)
    )
}

Write-Host "===== UPDATE RUNTIME ====="

foreach ($Component in @("khan_agent", "deploy", "tests")) {
    $Destination = Join-Path $Runtime $Component
    $Source = Join-Path $SourceDir $Component

    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }

    Copy-Item $Source $Destination -Recurse -Force
}

Write-Host "===== UPDATE CONFIG ====="

$ResolvedConfigFile = (Resolve-Path $ConfigFile).Path
$ResolvedInstalledConfig = $null

if (Test-Path $InstalledConfig -PathType Leaf) {
    $ResolvedInstalledConfig = (Resolve-Path $InstalledConfig).Path
}

if (
    $ResolvedInstalledConfig -and
    $ResolvedConfigFile -ieq $ResolvedInstalledConfig
) {
    Write-Host "Installed configuration already supplied - preserving existing config.yaml"
}
else {
    Copy-Item $ConfigFile $InstalledConfig -Force
}

Write-Host "===== COMPILE ====="

& $Python -m compileall -q (Join-Path $Runtime "khan_agent")

if ($LASTEXITCODE -ne 0) {
    throw "Python compile validation failed."
}

Write-Host "===== TESTS ====="

Push-Location $Runtime

try {
    & $Python -m pytest -q

    if ($LASTEXITCODE -ne 0) {
        throw "Node-agent test suite failed."
    }
}
finally {
    Pop-Location
}

Write-Host "===== START AGENT ====="

if ($Service) {
    Start-Service -Name $ServiceName

    (Get-Service -Name $ServiceName).WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(30)
    )
}

Write-Host "===== HEARTBEAT ====="

Push-Location $Runtime

try {
    & $Python `
        -m khan_agent `
        --config $InstalledConfig `
        --heartbeat-once

    if ($LASTEXITCODE -ne 0) {
        throw "Heartbeat verification failed."
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "SUCCESS: KHAN CLOUD WINDOWS NODE RUNTIME UPDATED"
Write-Host "Backup: $Backup"
Write-Host "credentials.json preserved"
Write-Host "identity.json preserved"
