param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [string]$ConfigFile,

    [string]$PythonExecutable = "",

    [switch]$BootstrapAuthorized
)

$ErrorActionPreference = "Stop"

$AgentRoot = Join-Path $env:ProgramData "KhanCloud\Agent"
$Runtime = Join-Path $AgentRoot "runtime"
$Credentials = Join-Path $AgentRoot "credentials.json"
$Identity = Join-Path $AgentRoot "identity.json"
$InstalledConfig = Join-Path $AgentRoot "config.yaml"
$ServiceName = "KhanCloudAgent"


# ------------------------------------------------------------
# INTERNAL ENTRYPOINT GUARD
# ------------------------------------------------------------
# install-runtime.ps1 is an internal execution engine. Provider
# bundles and operators must enter through universal-bootstrap.ps1,
# which owns prerequisite discovery/remediation and supplies the
# exact validated Python interpreter.
if (-not $BootstrapAuthorized) {
    throw (
        "Direct install-runtime.ps1 invocation is unsupported. " +
        "Run universal-bootstrap.ps1 instead."
    )
}

Write-Host "===== KHAN CLOUD WINDOWS AGENT INSTALLER ====="

# ------------------------------------------------------------
# PRE-FLIGHT
# ------------------------------------------------------------

Write-Host "===== PRE-FLIGHT ====="

if (-not $env:ProgramData) {
    throw "ProgramData environment variable is unavailable."
}

if (-not (Test-Path $SourceDir -PathType Container)) {
    throw "Source directory does not exist: $SourceDir"
}

if (-not (Test-Path $ConfigFile -PathType Leaf)) {
    throw "Configuration file does not exist: $ConfigFile"
}

foreach ($Component in @("khan_agent", "deploy", "tests")) {
    if (-not (Test-Path (Join-Path $SourceDir $Component))) {
        throw "Required runtime component is missing: $Component"
    }
}

$Requirements = Join-Path $SourceDir "requirements.txt"

if (-not (Test-Path $Requirements -PathType Leaf)) {
    throw "requirements.txt is missing: $Requirements"
}

# Python discovery and remediation belong exclusively to
# universal-bootstrap.ps1. The runtime installer receives the exact
# interpreter selected and validated by that bootstrap and must never
# rediscover Python from PATH.
if (-not (Test-Path $PythonExecutable -PathType Leaf)) {
    throw "Validated Python executable is unavailable: $PythonExecutable"
}

$SystemPython = $PythonExecutable

$PythonVersion = & $SystemPython `
    -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"

if ($LASTEXITCODE -ne 0) {
    throw "Validated Python executable failed: $SystemPython"
}

$VersionParts = $PythonVersion.Trim().Split(".")

if (
    [int]$VersionParts[0] -lt 3 -or
    (
        [int]$VersionParts[0] -eq 3 -and
        [int]$VersionParts[1] -lt 12
    )
) {
    throw "Python 3.12 or newer is required. Found $PythonVersion"
}

# ------------------------------------------------------------
# CREATE WINDOWS AGENT LAYOUT
# ------------------------------------------------------------

Write-Host "===== CREATE AGENT DIRECTORIES ====="

New-Item -ItemType Directory -Path $AgentRoot -Force | Out-Null
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null

# ------------------------------------------------------------
# PRESERVE NODE IDENTITY
# ------------------------------------------------------------

$HadCredentials = Test-Path $Credentials -PathType Leaf
$HadIdentity = Test-Path $Identity -PathType Leaf

if ($HadCredentials) {
    Write-Host "Existing credentials detected - node enrollment will be preserved."
}

if ($HadIdentity) {
    Write-Host "Existing identity detected - node UUID will be preserved."
}

# ------------------------------------------------------------
# DEPLOY MATCHING RUNTIME
# ------------------------------------------------------------

Write-Host "===== DEPLOY RUNTIME ====="

foreach ($Component in @("khan_agent", "deploy", "tests")) {
    $Source = Join-Path $SourceDir $Component
    $Destination = Join-Path $Runtime $Component

    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }

    Copy-Item $Source $Destination -Recurse -Force
}

Copy-Item $Requirements (Join-Path $Runtime "requirements.txt") -Force

$PyProject = Join-Path $SourceDir "pyproject.toml"

if (Test-Path $PyProject) {
    Copy-Item $PyProject (Join-Path $Runtime "pyproject.toml") -Force
}

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

Write-Host "===== INSTALL CONFIGURATION ====="

Copy-Item $ConfigFile $InstalledConfig -Force

# The Windows gaming-host profile uses:
# node_role: gaming_host
# execution_backend: windows_native
# streaming_backend: sunshine
#
# These values remain configuration-driven rather than hard-coded into
# the Python agent runtime.

# ------------------------------------------------------------
# PYTHON ENVIRONMENT
# ------------------------------------------------------------

Write-Host "===== CREATE PYTHON ENVIRONMENT ====="

$Venv = Join-Path $Runtime ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python -PathType Leaf)) {
    & $SystemPython -m venv $Venv

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create Python virtual environment."
    }
}

Write-Host "===== INSTALL DEPENDENCIES ====="

& $Python -m pip install --upgrade pip

if ($LASTEXITCODE -ne 0) {
    throw "Unable to upgrade pip."
}

& $Python -m pip install -r (Join-Path $Runtime "requirements.txt")

if ($LASTEXITCODE -ne 0) {
    throw "Unable to install Khan Cloud agent dependencies."
}

# ------------------------------------------------------------
# VALIDATION
# ------------------------------------------------------------

Write-Host "===== COMPILE ====="

& $Python -m compileall -q (Join-Path $Runtime "khan_agent")

if ($LASTEXITCODE -ne 0) {
    throw "Python compile validation failed."
}

Write-Host "===== TEST ====="

Push-Location $Runtime

try {
    & $Python -m pytest -q

    if ($LASTEXITCODE -ne 0) {
        throw "Khan Cloud node-agent tests failed."
    }
}
finally {
    Pop-Location
}

# ------------------------------------------------------------
# ENROLLMENT
# ------------------------------------------------------------

Push-Location $Runtime

try {
    if (-not (Test-Path $Credentials -PathType Leaf)) {
        Write-Host "===== FIRST-TIME NODE ENROLLMENT ====="

        & $Python `
            -m khan_agent `
            --config $InstalledConfig `
            --enroll

        if ($LASTEXITCODE -ne 0) {
            throw "Khan Cloud node enrollment failed."
        }

        if (-not (Test-Path $Credentials -PathType Leaf)) {
            throw "Enrollment completed without creating credentials.json."
        }

        if (-not (Test-Path $Identity -PathType Leaf)) {
            throw "Enrollment completed without creating identity.json."
        }

    }
    else {
        Write-Host "Existing credentials found - skipping enrollment."
    }

    # The deployment enrollment code is always one-time material.
    # Scrub it even when persistent credentials already exist, because
    # a reinstall/update may have copied a fresh config containing a code.
    $ScrubScript = @'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) or {}

security = data.setdefault("security", {})
security["deployment_enrollment_code"] = ""

path.write_text(yaml.safe_dump(data, sort_keys=False))
'@

    $ScrubScript | & $Python - $InstalledConfig

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to scrub deployment_enrollment_code."
    }
}
finally {
    Pop-Location
}

# ------------------------------------------------------------
# WINDOWS SERVICE
# ------------------------------------------------------------

Write-Host "===== INSTALL WINDOWS SERVICE ====="

$ServiceModule = Join-Path $Runtime "khan_agent\windows_service.py"

if (-not (Test-Path $ServiceModule -PathType Leaf)) {
    throw "Windows service host is missing: $ServiceModule"
}

$ServicePython = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $ServicePython -PathType Leaf)) {
    throw "Windows service Python is missing: $ServicePython"
}

$ExistingService = Get-Service `
    -Name $ServiceName `
    -ErrorAction SilentlyContinue

if ($ExistingService) {
    if ($ExistingService.Status -ne "Stopped") {
        Stop-Service -Name $ServiceName -Force

        (Get-Service -Name $ServiceName).WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Stopped,
            [TimeSpan]::FromSeconds(30)
        )
    }

    sc.exe delete $ServiceName | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove existing Khan Cloud Windows service."
    }

    # Allow SCM to finish releasing the deleted service object.
    Start-Sleep -Seconds 2
}

$ServiceCommand = (
    '"' + $ServicePython + '" ' +
    '-m khan_agent.windows_service --service'
)

sc.exe create `
    $ServiceName `
    binPath= $ServiceCommand `
    start= auto `
    DisplayName= "Khan Cloud Agent" |
    Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Unable to create Khan Cloud Windows service."
}

sc.exe description `
    $ServiceName `
    "Khan Cloud managed node agent" |
    Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Unable to set Khan Cloud Windows service description."
}

Start-Service -Name $ServiceName

(Get-Service -Name $ServiceName).WaitForStatus(
    [System.ServiceProcess.ServiceControllerStatus]::Running,
    [TimeSpan]::FromSeconds(30)
)

$Service = Get-Service -Name $ServiceName -ErrorAction Stop

if ($Service.Status -ne "Running") {
    throw "Khan Cloud Windows service did not enter Running state."
}

# ------------------------------------------------------------
# HEARTBEAT
# ------------------------------------------------------------

Write-Host "===== VERIFY HEARTBEAT ====="

Push-Location $Runtime

try {
    & $Python `
        -m khan_agent `
        --config $InstalledConfig `
        --heartbeat-once

    if ($LASTEXITCODE -ne 0) {
        throw "Khan Cloud heartbeat verification failed."
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "SUCCESS: KHAN CLOUD WINDOWS AGENT INSTALLED"
Write-Host "Runtime:     $Runtime"
Write-Host "State:       $AgentRoot"
Write-Host "Config:      $InstalledConfig"
Write-Host "Credentials: $Credentials"
Write-Host "Identity:    $Identity"
Write-Host "Service:     $ServiceName"
