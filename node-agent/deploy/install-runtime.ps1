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
# WINDOWS RUNTIME UPGRADE TRANSACTION
# ------------------------------------------------------------

$RuntimeBackup = Join-Path $AgentRoot "runtime.rollback"
$ExistingServicePresent = $false
$ExistingServiceWasRunning = $false
$RuntimeBackupCreated = $false
$RuntimeTransactionActive = $false
$DependencyTimeoutSeconds = 600

function Stop-KhanCloudAgentForRuntimeMutation {
    $ExistingService = Get-Service `
        -Name $ServiceName `
        -ErrorAction SilentlyContinue

    if (-not $ExistingService) {
        Write-Host "Existing Khan Cloud service is absent."
        return
    }

    $script:ExistingServicePresent = $true

    if ($ExistingService.Status -eq "Running") {
        $script:ExistingServiceWasRunning = $true
    }

    if ($ExistingService.Status -ne "Stopped") {
        Write-Host (
            "Stopping Khan Cloud service before runtime mutation."
        )

        Stop-Service `
            -Name $ServiceName `
            -Force `
            -ErrorAction Stop

        (Get-Service -Name $ServiceName).WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Stopped,
            [TimeSpan]::FromSeconds(30)
        )
    }

    $Stopped = Get-Service `
        -Name $ServiceName `
        -ErrorAction Stop

    if ($Stopped.Status -ne "Stopped") {
        throw (
            "Khan Cloud service did not quiesce before runtime mutation."
        )
    }
}

function Invoke-BoundedPythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Description,

        [int]$TimeoutSeconds = 600
    )

    $OutputPath = Join-Path `
        $env:TEMP `
        ("khan-cloud-" + [guid]::NewGuid().ToString("N") + ".out")

    $ErrorPath = Join-Path `
        $env:TEMP `
        ("khan-cloud-" + [guid]::NewGuid().ToString("N") + ".err")

    $Process = $null
    $StandardOutput = $null
    $StandardError = $null

    try {
        $StartInfo = New-Object System.Diagnostics.ProcessStartInfo

        $StartInfo.FileName = $PythonPath
        $StartInfo.UseShellExecute = $false
        $StartInfo.CreateNoWindow = $true
        $StartInfo.RedirectStandardOutput = $true
        $StartInfo.RedirectStandardError = $true

        # Windows PowerShell 5.1 does not expose
        # ProcessStartInfo.ArgumentList. Quote every argument explicitly
        # for the Windows CreateProcess command-line contract.
        $QuotedArguments = @(
            foreach ($Argument in $Arguments) {
                $Value = [string]$Argument

                if (
                    $Value.Length -eq 0 -or
                    $Value -match '[\s"]'
                ) {
                    $Escaped = $Value -replace '(\\*)"', '$1$1\"'
                    $Escaped = $Escaped -replace '(\\+)$', '$1$1'

                    '"' + $Escaped + '"'
                }
                else {
                    $Value
                }
            }
        )

        $StartInfo.Arguments = $QuotedArguments -join " "

        $Process = New-Object System.Diagnostics.Process
        $Process.StartInfo = $StartInfo

        if (-not $Process.Start()) {
            throw "$Description failed to start."
        }

        $StandardOutput = $Process.StandardOutput.ReadToEndAsync()
        $StandardError = $Process.StandardError.ReadToEndAsync()

        $Completed = $Process.WaitForExit(
            $TimeoutSeconds * 1000
        )

        if (-not $Completed) {
            Write-Host (
                "$Description timed out after " +
                "$TimeoutSeconds seconds."
            )

            & taskkill.exe `
                /PID $Process.Id `
                /T `
                /F |
                Out-Null

            try {
                $Process.WaitForExit()
            }
            catch {
            }

            throw "$Description timed out."
        }

        $Process.WaitForExit()

        $ProcessExitCode = [int]$Process.ExitCode

        $OutputText = $StandardOutput.GetAwaiter().GetResult()
        $ErrorText = $StandardError.GetAwaiter().GetResult()

        if (-not [string]::IsNullOrEmpty($OutputText)) {
            [System.IO.File]::WriteAllText(
                $OutputPath,
                $OutputText
            )

            Get-Content -LiteralPath $OutputPath |
                Write-Host
        }

        if (-not [string]::IsNullOrEmpty($ErrorText)) {
            [System.IO.File]::WriteAllText(
                $ErrorPath,
                $ErrorText
            )

            Get-Content -LiteralPath $ErrorPath |
                Write-Host
        }

        if ($ProcessExitCode -ne 0) {
            throw (
                "$Description failed with exit code " +
                $ProcessExitCode +
                "."
            )
        }
    }
    finally {
        if ($Process) {
            $Process.Dispose()
        }

        Remove-Item `
            -LiteralPath $OutputPath,$ErrorPath `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

function Restore-KhanCloudRuntime {
    Write-Host "===== ROLLBACK WINDOWS RUNTIME ====="

    $CurrentService = Get-Service `
        -Name $ServiceName `
        -ErrorAction SilentlyContinue

    if (
        $CurrentService -and
        $CurrentService.Status -ne "Stopped"
    ) {
        Stop-Service `
            -Name $ServiceName `
            -Force `
            -ErrorAction SilentlyContinue

        try {
            (Get-Service -Name $ServiceName).WaitForStatus(
                [System.ServiceProcess.ServiceControllerStatus]::Stopped,
                [TimeSpan]::FromSeconds(30)
            )
        }
        catch {
            Write-Warning (
                "Service stop during rollback could not be verified."
            )
        }
    }

    if (Test-Path $Runtime -PathType Container) {
        Remove-Item `
            $Runtime `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }

    if ($script:RuntimeBackupCreated) {
        if (-not (Test-Path $RuntimeBackup -PathType Container)) {
            throw "Runtime rollback backup is missing."
        }

        Move-Item `
            $RuntimeBackup `
            $Runtime `
            -Force `
            -ErrorAction Stop
    }

    if (
        -not $script:ExistingServicePresent
    ) {
        $CreatedService = Get-Service `
            -Name $ServiceName `
            -ErrorAction SilentlyContinue

        if ($CreatedService) {
            & sc.exe delete $ServiceName |
                Out-Null
        }
    }
    elseif ($script:ExistingServiceWasRunning) {
        Start-Service `
            -Name $ServiceName `
            -ErrorAction Stop

        (Get-Service -Name $ServiceName).WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Running,
            [TimeSpan]::FromSeconds(30)
        )
    }
}

try {
    Write-Host "===== QUIESCE EXISTING WINDOWS SERVICE ====="

    Stop-KhanCloudAgentForRuntimeMutation

    Write-Host "===== BACKUP EXISTING RUNTIME ====="

    if (Test-Path $RuntimeBackup) {
        Remove-Item `
            $RuntimeBackup `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }

    if (Test-Path $Runtime -PathType Container) {
        Move-Item `
            $Runtime `
            $RuntimeBackup `
            -Force `
            -ErrorAction Stop

        $RuntimeBackupCreated = $true
    }

    $RuntimeTransactionActive = $true
}
catch {
    $PreparationFailure = $_

    if ($ExistingServiceWasRunning) {
        $ServiceAfterPreparationFailure = Get-Service `
            -Name $ServiceName `
            -ErrorAction SilentlyContinue

        if (
            $ServiceAfterPreparationFailure -and
            $ServiceAfterPreparationFailure.Status -ne "Running"
        ) {
            try {
                Start-Service `
                    -Name $ServiceName `
                    -ErrorAction Stop

                (Get-Service -Name $ServiceName).WaitForStatus(
                    [System.ServiceProcess.ServiceControllerStatus]::Running,
                    [TimeSpan]::FromSeconds(30)
                )
            }
            catch {
                Write-Error (
                    "Failed to restore Khan Cloud service after " +
                    "transaction preparation failure: " +
                    $_.Exception.Message
                )
            }
        }
    }

    throw $PreparationFailure
}

try {

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

$ConfigSourceFullPath = (
    [System.IO.Path]::GetFullPath($ConfigFile)
).TrimEnd("\")

$InstalledConfigFullPath = (
    [System.IO.Path]::GetFullPath($InstalledConfig)
).TrimEnd("\")

$ConfigAlreadyInstalled = [string]::Equals(
    $ConfigSourceFullPath,
    $InstalledConfigFullPath,
    [System.StringComparison]::OrdinalIgnoreCase
)

if ($ConfigAlreadyInstalled) {
    Write-Host (
        "Configuration source already matches installed target - " +
        "preserving config.yaml in place."
    )
}
else {
    Copy-Item $ConfigFile $InstalledConfig -Force
}

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

Invoke-BoundedPythonCommand `
    -PythonPath $Python `
    -Arguments @(
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
        "pip"
    ) `
    -Description "Python pip upgrade" `
    -TimeoutSeconds $DependencyTimeoutSeconds

Invoke-BoundedPythonCommand `
    -PythonPath $Python `
    -Arguments @(
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "-r",
        (Join-Path $Runtime "requirements.txt")
    ) `
    -Description "Khan Cloud dependency installation" `
    -TimeoutSeconds $DependencyTimeoutSeconds

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
    & $Python -m pytest -q -m "not source_tree_only"

    if ($LASTEXITCODE -ne 0) {
        throw "Khan Cloud node-agent tests failed."
    }
}
finally {
    Pop-Location
}

# ------------------------------------------------------------
# WINDOWS SUNSHINE PROTECTED CREDENTIAL
# ------------------------------------------------------------

Write-Host "===== CONFIGURE SUNSHINE PROTECTED CREDENTIAL ====="

$SunshinePolicyScript = Join-Path `
    $Runtime `
    "deploy\configure-windows-sunshine.ps1"

if (-not (Test-Path $SunshinePolicyScript -PathType Leaf)) {
    throw (
        "Sunshine credential configurator is missing: " +
        $SunshinePolicyScript
    )
}

$SunshinePolicyReader = @'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) or {}
gaming = data.get("gaming") or {}

enabled = bool(
    gaming.get("enabled", False)
)

backend = str(
    gaming.get("streaming_backend", "none")
).strip().lower()

source = str(
    gaming.get(
        "sunshine_credential_source",
        "config",
    )
).strip().lower()

username = str(
    gaming.get(
        "sunshine_api_username",
        "",
    )
).strip()

secret_name = str(
    gaming.get(
        "sunshine_secret_name",
        "KhanCloudSunshineApiPassword",
    )
).strip()

api_url = str(
    gaming.get(
        "sunshine_api_url",
        "https://127.0.0.1:47990",
    )
).strip()

verify_tls = bool(
    gaming.get(
        "sunshine_verify_tls",
        False,
    )
)

plaintext_password = str(
    gaming.get(
        "sunshine_api_password",
        "",
    )
)

print(
    "|".join(
        [
            "1" if enabled else "0",
            backend,
            source,
            username,
            secret_name,
            api_url,
            "1" if verify_tls else "0",
            "1" if plaintext_password else "0",
        ]
    )
)
'@

$SunshinePolicyValue = (
    $SunshinePolicyReader |
    & $Python - $InstalledConfig
)

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Sunshine credential policy."
}

$SunshineParts = (
    [string]$SunshinePolicyValue
).Trim().Split("|", 8)

if ($SunshineParts.Count -ne 8) {
    throw "Sunshine credential policy is invalid."
}

$SunshineGamingEnabled =
    ($SunshineParts[0] -eq "1")

$SunshineBackend =
    $SunshineParts[1].Trim().ToLowerInvariant()

$SunshineCredentialSource =
    $SunshineParts[2].Trim().ToLowerInvariant()

$SunshineUser =
    $SunshineParts[3].Trim()

$SunshineSecretName =
    $SunshineParts[4].Trim()

$SunshineApiUrl =
    $SunshineParts[5].Trim()

$SunshineVerifyTls =
    ($SunshineParts[6] -eq "1")

$SunshineHasPlaintextPassword =
    ($SunshineParts[7] -eq "1")

if (
    $SunshineGamingEnabled -and
    $SunshineBackend -eq "sunshine"
) {
    if (
        $SunshineCredentialSource -eq "windows_lsa"
    ) {
        if ($SunshineHasPlaintextPassword) {
            throw (
                "Sunshine Windows LSA credential policy " +
                "must not contain sunshine_api_password."
            )
        }

        if ([string]::IsNullOrWhiteSpace($SunshineUser)) {
            throw (
                "Sunshine Windows LSA credential policy " +
                "requires sunshine_api_username."
            )
        }

        if ([string]::IsNullOrWhiteSpace($SunshineSecretName)) {
            throw (
                "Sunshine Windows LSA credential policy " +
                "requires sunshine_secret_name."
            )
        }

        if ([string]::IsNullOrWhiteSpace($SunshineApiUrl)) {
            throw (
                "Sunshine Windows LSA credential policy " +
                "requires sunshine_api_url."
            )
        }

        $SunshineArguments = @(
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $SunshinePolicyScript,
            "-Action",
            "Configure",
            "-UserName",
            $SunshineUser,
            "-SecretName",
            $SunshineSecretName,
            "-ApiUrl",
            $SunshineApiUrl,
            "-PythonPath",
            $Python
        )

        if ($SunshineVerifyTls) {
            $SunshineArguments += "-VerifyTls"
        }

        & powershell.exe @SunshineArguments

        if ($LASTEXITCODE -ne 0) {
            throw (
                "Sunshine protected credential " +
                "configuration failed."
            )
        }
    }
    elseif (
        $SunshineCredentialSource -ne "config"
    ) {
        throw (
            "Unsupported sunshine_credential_source: " +
            $SunshineCredentialSource
        )
    }
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
# WINDOWS INTERACTIVE SESSION BROKER
# ------------------------------------------------------------

Write-Host "===== CONFIGURE WINDOWS GAMING SESSION BROKER ====="

$BrokerPolicyScript = Join-Path `
    $Runtime `
    "deploy\configure-windows-gaming-session.ps1"

if (-not (Test-Path $BrokerPolicyScript -PathType Leaf)) {
    throw (
        "Windows gaming session broker configurator is missing: " +
        $BrokerPolicyScript
    )
}

$BrokerPolicy = @'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) or {}
gaming = data.get("gaming") or {}

enabled = bool(gaming.get("enabled", False))
mode = str(
    gaming.get("session_broker_mode", "existing")
).strip().lower()

username = str(
    gaming.get("session_broker_username", "KhanGaming")
).strip()

print(
    ("1" if enabled else "0")
    + "|"
    + mode
    + "|"
    + username
)
'@

$BrokerPolicyValue = (
    $BrokerPolicy |
    & $Python - $InstalledConfig
)

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Windows gaming session broker policy."
}

$BrokerParts = (
    [string]$BrokerPolicyValue
).Trim().Split("|", 3)

if ($BrokerParts.Count -ne 3) {
    throw "Windows gaming session broker policy is invalid."
}

$GamingEnabled = ($BrokerParts[0] -eq "1")
$SessionBrokerMode = $BrokerParts[1].Trim().ToLowerInvariant()
$SessionBrokerUser = $BrokerParts[2].Trim()

$AllowedBrokerModes = @(
    "existing",
    "managed_autologon"
)

if ($SessionBrokerMode -notin $AllowedBrokerModes) {
    throw (
        "Unsupported Windows gaming session_broker_mode: " +
        $SessionBrokerMode
    )
}

if (
    $GamingEnabled -and
    $SessionBrokerMode -eq "managed_autologon"
) {
    if ([string]::IsNullOrWhiteSpace($SessionBrokerUser)) {
        throw (
            "Managed Windows gaming session requires " +
            "session_broker_username."
        )
    }

    & $BrokerPolicyScript `
        -Action Configure `
        -UserName $SessionBrokerUser

    if ($LASTEXITCODE -ne 0) {
        throw "Windows gaming session broker configuration failed."
    }

    Write-Host (
        "SESSION_BROKER=managed_autologon:" +
        $SessionBrokerUser
    )
}
else {
    & $BrokerPolicyScript `
        -Action Deconfigure `
        -UserName $SessionBrokerUser

    if ($LASTEXITCODE -ne 0) {
        throw (
            "Windows gaming session broker deconfiguration failed."
        )
    }

    Write-Host (
        "SESSION_BROKER=" +
        $SessionBrokerMode
    )
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

if (
    $ExistingService -and
    $ExistingService.Status -ne "Stopped"
) {
    throw (
        "Existing Khan Cloud service unexpectedly resumed " +
        "during runtime installation."
    )
}

$ServiceCommand = (
    '"' + $ServicePython + '" ' +
    '"' + $ServiceModule + '" --service'
)

if (-not $ExistingService) {
    sc.exe create `
        $ServiceName `
        binPath= $ServiceCommand `
        start= auto `
        DisplayName= "Khan Cloud Agent" |
        Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create Khan Cloud Windows service."
    }
}
else {
    sc.exe config `
        $ServiceName `
        binPath= $ServiceCommand `
        start= auto |
        Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to update Khan Cloud Windows service."
    }
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

Write-Host "===== COMMIT RUNTIME TRANSACTION ====="

if (Test-Path $RuntimeBackup) {
    Remove-Item `
        $RuntimeBackup `
        -Recurse `
        -Force
}

$RuntimeTransactionActive = $false

Write-Host ""
Write-Host "SUCCESS: KHAN CLOUD WINDOWS AGENT INSTALLED"
Write-Host "Runtime:     $Runtime"
Write-Host "State:       $AgentRoot"
Write-Host "Config:      $InstalledConfig"
Write-Host "Credentials: $Credentials"
Write-Host "Identity:    $Identity"
Write-Host "Service:     $ServiceName"

}
catch {
    $InstallFailure = $_

    if ($RuntimeTransactionActive) {
        try {
            Restore-KhanCloudRuntime
        }
        catch {
            Write-Error (
                "Runtime rollback failed: " +
                $_.Exception.Message
            )
        }
    }

    throw $InstallFailure
}
