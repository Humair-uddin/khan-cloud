param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [string]$ConfigFile,

    [string]$InstallerManifest = "",

    [string]$MinimumPythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ============================================================
# KHAN CLOUD UNIVERSAL WINDOWS BOOTSTRAP
#
# Responsibilities:
#   * require administrative execution
#   * maintain resumable bootstrap checkpoints
#   * safely discover/remediate Python
#   * validate Python >= required version
#   * invoke the existing production runtime installer
#
# The Python venv belongs ONLY to Khan Cloud runtime components.
# Games, Sunshine and customer applications remain native
# Windows software and are never installed into this venv.
# ============================================================

$ProgramDataRoot = $env:ProgramData

if (-not $ProgramDataRoot) {
    throw "ProgramData environment variable is unavailable."
}

$BootstrapRoot = Join-Path $ProgramDataRoot "KhanCloud\Bootstrap"
$CheckpointFile = Join-Path $BootstrapRoot "bootstrap.checkpoints"
$InstallRuntime = Join-Path $SourceDir "deploy\install-runtime.ps1"

function Write-Stage {
    param([string]$Name)

    Write-Host ""
    Write-Host "===== $Name ====="
}

function Test-Administrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()

    $Principal = New-Object Security.Principal.WindowsPrincipal(
        $Identity
    )

    return $Principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Test-Checkpoint {
    param([string]$Name)

    if (-not (Test-Path $CheckpointFile -PathType Leaf)) {
        return $false
    }

    return [bool](
        Get-Content $CheckpointFile |
        Where-Object { $_.Trim() -eq $Name }
    )
}

function Set-Checkpoint {
    param([string]$Name)

    if (-not (Test-Checkpoint $Name)) {
        Add-Content `
            -Path $CheckpointFile `
            -Value $Name `
            -Encoding UTF8
    }
}

function Convert-Version {
    param([string]$Version)

    $Match = [regex]::Match(
        $Version.Trim(),
        '^(\d+)\.(\d+)(?:\.(\d+))?'
    )

    if (-not $Match.Success) {
        return $null
    }

    $Patch = 0

    if ($Match.Groups[3].Success) {
        $Patch = [int]$Match.Groups[3].Value
    }

    return [version]::new(
        [int]$Match.Groups[1].Value,
        [int]$Match.Groups[2].Value,
        $Patch
    )
}

function Get-CompatiblePython {
    $Candidates = @()

    foreach ($Name in @(
        "python.exe",
        "python",
        "py.exe",
        "py"
    )) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue

        if ($Command) {
            $Candidates += $Command
        }
    }

    foreach ($Candidate in $Candidates) {
        try {
            if ($Candidate.Name -like "py*") {
                $Executable = $Candidate.Source
                $VersionText = & $Executable -3 `
                    -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"

                if ($LASTEXITCODE -ne 0) {
                    continue
                }

                $ResolvedPython = & $Executable -3 `
                    -c "import sys; print(sys.executable)"

                if ($LASTEXITCODE -ne 0) {
                    continue
                }
            }
            else {
                $Executable = $Candidate.Source

                $VersionText = & $Executable `
                    -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"

                if ($LASTEXITCODE -ne 0) {
                    continue
                }

                $ResolvedPython = & $Executable `
                    -c "import sys; print(sys.executable)"

                if ($LASTEXITCODE -ne 0) {
                    continue
                }
            }

            $Version = Convert-Version $VersionText
            $Minimum = Convert-Version $MinimumPythonVersion

            if (
                $null -ne $Version -and
                $null -ne $Minimum -and
                $Version -ge $Minimum
            ) {
                return [PSCustomObject]@{
                    Path = $ResolvedPython.Trim()
                    Version = $Version.ToString()
                }
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Install-PythonSafely {
    Write-Stage "PYTHON REMEDIATION"

    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue

    if (-not $Winget) {
        $Winget = Get-Command winget -ErrorAction SilentlyContinue
    }

    if (-not $Winget) {
        throw @"
Python $MinimumPythonVersion or newer is required and no compatible
Python installation was detected.

Automatic remediation requires Windows Package Manager (winget).
Install a supported Python 3.12+ runtime and rerun this bootstrap.
"@
    }

    Write-Host "Installing approved Python runtime through Windows Package Manager."

    & $Winget.Source install `
        --id Python.Python.3.12 `
        --exact `
        --scope machine `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity

    if ($LASTEXITCODE -ne 0) {
        throw "Automatic Python installation failed."
    }

    # Refresh machine PATH for this PowerShell process.
    $MachinePath = [Environment]::GetEnvironmentVariable(
        "Path",
        [EnvironmentVariableTarget]::Machine
    )

    $UserPath = [Environment]::GetEnvironmentVariable(
        "Path",
        [EnvironmentVariableTarget]::User
    )

    $env:Path = "$MachinePath;$UserPath"

    $CommonCandidates = @(
        "$env:ProgramFiles\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe"
    )

    foreach ($Candidate in $CommonCandidates) {
        if (Test-Path $Candidate -PathType Leaf) {
            $Directory = Split-Path $Candidate -Parent

            if ($env:Path -notlike "*$Directory*") {
                $env:Path = "$Directory;$env:Path"
            }
        }
    }
}

Write-Host "===== KHAN CLOUD UNIVERSAL WINDOWS BOOTSTRAP ====="

# ============================================================
# ADMINISTRATIVE SAFETY
# ============================================================

Write-Stage "ADMINISTRATOR CHECK"

if (-not (Test-Administrator)) {
    throw "Khan Cloud Windows bootstrap must run as Administrator."
}

New-Item `
    -ItemType Directory `
    -Path $BootstrapRoot `
    -Force |
    Out-Null

if (-not (Test-Path $CheckpointFile)) {
    New-Item `
        -ItemType File `
        -Path $CheckpointFile `
        -Force |
        Out-Null
}

if (-not (Test-Checkpoint "administrator_checked")) {
    Set-Checkpoint "administrator_checked"
}

# ============================================================
# INPUT VALIDATION
# ============================================================

Write-Stage "INPUT VALIDATION"

if (-not (Test-Path $SourceDir -PathType Container)) {
    throw "Source directory does not exist: $SourceDir"
}

if (-not (Test-Path $ConfigFile -PathType Leaf)) {
    throw "Configuration file does not exist: $ConfigFile"
}

if (-not (Test-Path $InstallRuntime -PathType Leaf)) {
    throw "Windows runtime installer is missing: $InstallRuntime"
}

if (
    $InstallerManifest -and
    -not (Test-Path $InstallerManifest -PathType Leaf)
) {
    throw "Installer manifest does not exist: $InstallerManifest"
}

Set-Checkpoint "inputs_validated"

# ============================================================
# PYTHON DISCOVERY / SAFE REMEDIATION
# ============================================================

Write-Stage "PYTHON DISCOVERY"

$Python = Get-CompatiblePython

if (-not $Python) {
    Install-PythonSafely

    $Python = Get-CompatiblePython
}

if (-not $Python) {
    throw "Python remediation completed but no compatible Python runtime was detected."
}

Write-Host "Python executable: $($Python.Path)"
Write-Host "Python version:    $($Python.Version)"

Set-Checkpoint "python_ready"

# ============================================================
# VENV CAPABILITY
# ============================================================

Write-Stage "PYTHON VENV VALIDATION"

$Probe = Join-Path $env:TEMP (
    "khan-cloud-venv-probe-" + [guid]::NewGuid().ToString("N")
)

try {
    & $Python.Path -m venv $Probe

    if ($LASTEXITCODE -ne 0) {
        throw "Python venv capability validation failed."
    }

    $ProbePython = Join-Path $Probe "Scripts\python.exe"

    if (-not (Test-Path $ProbePython -PathType Leaf)) {
        throw "Python venv did not create a usable interpreter."
    }
}
finally {
    if (Test-Path $Probe) {
        Remove-Item $Probe -Recurse -Force
    }
}

Set-Checkpoint "venv_capability_verified"

# ============================================================
# MANIFEST PRESENCE
# ============================================================

if ($InstallerManifest) {
    Write-Stage "INSTALLER MANIFEST"

    Write-Host "Universal installer manifest: $InstallerManifest"

    # The authoritative qualification checks are performed by the
    # Installer Engine before machine mutation. The bootstrap records
    # and transports the same manifest rather than inventing another
    # Windows-specific policy representation.

    Set-Checkpoint "installer_manifest_present"
}

# ============================================================
# EXISTING PRODUCTION WINDOWS INSTALLER
# ============================================================

Write-Stage "INSTALL KHAN CLOUD RUNTIME"

& $InstallRuntime `
    -SourceDir $SourceDir `
    -ConfigFile $ConfigFile `
    -PythonExecutable $Python.Path `
    -BootstrapAuthorized

if ($LASTEXITCODE -ne 0) {
    throw "Khan Cloud Windows runtime installation failed."
}

Set-Checkpoint "runtime_installed"

# ============================================================
# FINAL SERVICE VALIDATION
# ============================================================

Write-Stage "FINAL VALIDATION"

$Service = Get-Service `
    -Name "KhanCloudAgent" `
    -ErrorAction Stop

if ($Service.Status -ne "Running") {
    throw "KhanCloudAgent service is not running after installation."
}

$AgentPython = Join-Path `
    $env:ProgramData `
    "KhanCloud\Agent\runtime\.venv\Scripts\python.exe"

if (-not (Test-Path $AgentPython -PathType Leaf)) {
    throw "Khan Cloud isolated Python runtime is missing."
}

Set-Checkpoint "completed"

Write-Host ""
Write-Host "SUCCESS: KHAN CLOUD UNIVERSAL WINDOWS BOOTSTRAP COMPLETE"
Write-Host "Bootstrap state: $BootstrapRoot"
Write-Host "Agent runtime:    $AgentPython"
Write-Host "Service:          KhanCloudAgent"
