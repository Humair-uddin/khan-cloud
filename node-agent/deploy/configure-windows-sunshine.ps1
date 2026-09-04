param(
    [ValidateSet("Configure", "Validate")]
    [string]$Action = "Configure",

    [string]$UserName = "KhanCloud",

    [string]$SecretName = "KhanCloudSunshineApiPassword",

    [string]$ApiUrl = "https://127.0.0.1:47990",

    [switch]$VerifyTls,

    [string]$PythonPath = "",

    [string]$SunshinePath = (
        "C:\Program Files\Sunshine\sunshine.exe"
    ),

    [string]$StatePath = (
        Join-Path `
            $env:ProgramData `
            "KhanCloud\Agent\sunshine-credential.json"
    )
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()

    $principal = New-Object `
        Security.Principal.WindowsPrincipal($identity)

    if (
        -not $principal.IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator
        )
    ) {
        throw (
            "Sunshine protected credential configuration " +
            "must run as Administrator."
        )
    }
}

function New-KhanCloudSunshinePassword {
    param([int]$Bytes = 48)

    $buffer = New-Object byte[] $Bytes

    $rng =
        [Security.Cryptography.RandomNumberGenerator]::Create()

    try {
        $rng.GetBytes($buffer)
    }
    finally {
        $rng.Dispose()
    }

    return (
        [Convert]::ToBase64String($buffer) +
        "!aA9"
    )
}

function Test-SunshineAuthenticatedApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [string]$ApiUser,

        [Parameter(Mandatory = $true)]
        [string]$ApiPassword,

        [bool]$ValidateTls,

        [string]$PythonExecutable = ""
    )

    $endpoint =
        $Uri.TrimEnd("/") +
        "/api/clients/list"

    if (-not $ValidateTls) {
        if (
            [string]::IsNullOrWhiteSpace(
                $PythonExecutable
            ) -or
            -not (
                Test-Path `
                    -LiteralPath $PythonExecutable `
                    -PathType Leaf
            )
        ) {
            throw (
                "A valid PythonPath is required for " +
                "Sunshine verification when TLS " +
                "certificate validation is disabled."
            )
        }

        $probePath =
            Join-Path `
                $env:TEMP `
                (
                    "khan-sunshine-auth-" +
                    [Guid]::NewGuid().ToString("N") +
                    ".py"
                )

        $probeLines = @(
            "import base64",
            "import json",
            "import ssl",
            "import sys",
            "import urllib.error",
            "import urllib.request",
            "",
            "payload = json.loads(sys.stdin.read())",
            "url = payload['url']",
            "username = payload['username']",
            "password = payload['password']",
            "",
            "token = base64.b64encode(",
            "    f'{username}:{password}'.encode('utf-8')",
            ").decode('ascii')",
            "",
            "request = urllib.request.Request(",
            "    url,",
            "    headers={'Authorization': f'Basic {token}'},",
            ")",
            "",
            "context = ssl._create_unverified_context()",
            "",
            "try:",
            "    with urllib.request.urlopen(",
            "        request,",
            "        context=context,",
            "        timeout=10,",
            "    ) as response:",
            "        raise SystemExit(",
            "            0 if 200 <= response.status < 300 else 1",
            "        )",
            "except urllib.error.HTTPError:",
            "    raise SystemExit(1)",
            "except Exception:",
            "    raise SystemExit(2)"
        )

        try {
            $utf8NoBom =
                New-Object `
                    System.Text.UTF8Encoding($false)

            [System.IO.File]::WriteAllLines(
                $probePath,
                $probeLines,
                $utf8NoBom
            )

            $payload =
                @{
                    url = $endpoint
                    username = $ApiUser
                    password = $ApiPassword
                } |
                ConvertTo-Json -Compress

            $startInfo =
                New-Object `
                    System.Diagnostics.ProcessStartInfo

            $startInfo.FileName =
                $PythonExecutable

            $startInfo.Arguments =
                '"' +
                $probePath.Replace('"', '\"') +
                '"'

            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true

            $startInfo.RedirectStandardInput =
                $true

            $startInfo.RedirectStandardOutput =
                $true

            $startInfo.RedirectStandardError =
                $true

            $process =
                New-Object `
                    System.Diagnostics.Process

            $process.StartInfo = $startInfo

            if (-not $process.Start()) {
                return $false
            }

            try {
                $process.StandardInput.Write(
                    $payload
                )

                $process.StandardInput.Close()

                if (
                    -not $process.WaitForExit(
                        15000
                    )
                ) {
                    try {
                        $process.Kill()
                    }
                    catch {
                    }

                    return $false
                }

                return (
                    [int]$process.ExitCode -eq 0
                )
            }
            finally {
                $process.Dispose()
                $payload = $null
            }
        }
        catch {
            return $false
        }
        finally {
            Remove-Item `
                -LiteralPath $probePath `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    # TLS-validating installations retain the native
    # PowerShell HTTPS path.
    $pair =
        $ApiUser + ":" + $ApiPassword

    $bytes =
        [Text.Encoding]::UTF8.GetBytes(
            $pair
        )

    $authorization =
        "Basic " +
        [Convert]::ToBase64String(
            $bytes
        )

    try {
        try {
            $response =
                Invoke-WebRequest `
                    -Uri $endpoint `
                    -Headers @{
                        Authorization = $authorization
                    } `
                    -Method Get `
                    -UseBasicParsing `
                    -TimeoutSec 10 `
                    -ErrorAction Stop

            return (
                [int]$response.StatusCode -ge 200 -and
                [int]$response.StatusCode -lt 300
            )
        }
        catch {
            return $false
        }
    }
    finally {
        $pair = $null
        $bytes = $null
        $authorization = $null
    }
}

function Write-CredentialState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,

        [Parameter(Mandatory = $true)]
        [bool]$Authenticated
    )

    $directory =
        Split-Path `
            -Parent `
            $StatePath

    New-Item `
        -ItemType Directory `
        -Path $directory `
        -Force |
        Out-Null

    $state = [ordered]@{
        contract_version = "kg009d3-sunshine-credential-v1"
        managed = $true
        status = $Status
        username = $UserName
        secret_store = "lsa_private_data"
        secret_name = $SecretName
        plaintext_config_password = $false
        authenticated_api = $Authenticated
        configured_at_utc = (
            [DateTime]::UtcNow.ToString("o")
        )
    }

    $json =
        $state |
        ConvertTo-Json -Depth 5

    $temp =
        "$StatePath.tmp"

    $utf8NoBom =
        New-Object `
            System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $temp,
        $json,
        $utf8NoBom
    )

    Move-Item `
        -LiteralPath $temp `
        -Destination $StatePath `
        -Force
}

Write-Host "============================================================"
Write-Host " KHAN CLOUD - PROTECTED SUNSHINE CREDENTIAL"
Write-Host "============================================================"

Assert-Administrator

if ([string]::IsNullOrWhiteSpace($UserName)) {
    throw "Sunshine API username cannot be blank."
}

if ([string]::IsNullOrWhiteSpace($SecretName)) {
    throw "Sunshine protected-secret name cannot be blank."
}

if ([string]::IsNullOrWhiteSpace($ApiUrl)) {
    throw "Sunshine API URL cannot be blank."
}

$LsaHelper =
    Join-Path `
        $PSScriptRoot `
        "windows-lsa-secret.ps1"

if (-not (Test-Path $LsaHelper -PathType Leaf)) {
    throw (
        "Khan Cloud Windows LSA helper is missing: " +
        $LsaHelper
    )
}

. $LsaHelper

$secret =
    [KhanLsaSecret]::Retrieve(
        $SecretName
    )

if ($Action -eq "Validate") {
    if ([string]::IsNullOrEmpty($secret)) {
        throw "Protected Sunshine credential is absent."
    }

    $ready =
        Test-SunshineAuthenticatedApi `
            -Uri $ApiUrl `
            -ApiUser $UserName `
            -ApiPassword $secret `
            -ValidateTls ([bool]$VerifyTls) `
            -PythonExecutable $PythonPath

    if (-not $ready) {
        throw (
            "Protected Sunshine credential failed " +
            "authenticated API validation."
        )
    }

    Write-Host "PROTECTED_SECRET_PRESENT=YES"
    Write-Host "SUNSHINE_AUTHENTICATED_API=PASS"
    Write-Host "SUNSHINE_CREDENTIAL_ROTATED=NO"
    Write-Host "SECRET_VALUE_PRINTED=NO"
    Write-Host "KG009D3_SUNSHINE_CREDENTIAL_VALIDATION=PASS"
    exit 0
}

if (-not (Test-Path $SunshinePath -PathType Leaf)) {
    throw (
        "Sunshine executable is missing: " +
        $SunshinePath
    )
}

$secretCreated = $false
$credentialChanged = $false

if ([string]::IsNullOrEmpty($secret)) {
    $secret =
        New-KhanCloudSunshinePassword

    [KhanLsaSecret]::Store(
        $SecretName,
        $secret
    )

    $secretCreated = $true

    Write-Host "PROTECTED_SECRET_CREATED=YES"
}
else {
    Write-Host "PROTECTED_SECRET_CREATED=NO"
}

$ready =
    Test-SunshineAuthenticatedApi `
        -Uri $ApiUrl `
        -ApiUser $UserName `
        -ApiPassword $secret `
        -ValidateTls ([bool]$VerifyTls) `
            -PythonExecutable $PythonPath

if ($ready) {
    Write-CredentialState `
        -Status "ready" `
        -Authenticated $true

    Write-Host "SUNSHINE_CREDENTIAL_PRESERVED=YES"
    Write-Host "SUNSHINE_CREDENTIAL_ROTATED=NO"
    Write-Host "SUNSHINE_AUTHENTICATED_API=PASS"
    Write-Host "SECRET_VALUE_PRINTED=NO"
    Write-Host "KG009D3_SUNSHINE_CREDENTIAL_CONFIGURATION=PASS"
    exit 0
}

try {
    # The installed Sunshine build was locally verified to expose:
    # --creds username password
    #
    # Do not echo the generated credential or command line.
    & $SunshinePath `
        --creds `
        $UserName `
        $secret `
        *> $null

    $sunshineExitCode =
        [int]$LASTEXITCODE

    if ($sunshineExitCode -ne 0) {
        throw (
            "Sunshine credential command failed with exit code " +
            $sunshineExitCode +
            "."
        )
    }

    $credentialChanged = $true

    $ready =
        Test-SunshineAuthenticatedApi `
            -Uri $ApiUrl `
            -ApiUser $UserName `
            -ApiPassword $secret `
            -ValidateTls ([bool]$VerifyTls) `
            -PythonExecutable $PythonPath

    $sunshineServiceRestarted = $false

    if (-not $ready) {
        $sunshineService =
            Get-Service `
                -Name "SunshineService" `
                -ErrorAction SilentlyContinue

        if (
            $sunshineService -and
            $sunshineService.Status -eq "Running"
        ) {
            Restart-Service `
                -Name "SunshineService" `
                -Force `
                -ErrorAction Stop

            (Get-Service -Name "SunshineService").WaitForStatus(
                [System.ServiceProcess.ServiceControllerStatus]::Running,
                [TimeSpan]::FromSeconds(30)
            )

            $sunshineServiceRestarted = $true

            $ready =
                Test-SunshineAuthenticatedApi `
                    -Uri $ApiUrl `
                    -ApiUser $UserName `
                    -ApiPassword $secret `
                    -ValidateTls ([bool]$VerifyTls) `
            -PythonExecutable $PythonPath
        }
    }

    if (-not $ready) {
        Write-CredentialState `
            -Status "repair_required" `
            -Authenticated $false

        throw (
            "Sunshine accepted the credential command but " +
            "the authenticated API could not be verified " +
            "with the protected credential."
        )
    }

    Write-CredentialState `
        -Status "ready" `
        -Authenticated $true
}
catch {
    if (
        $secretCreated -or
        $credentialChanged
    ) {
        Write-CredentialState `
            -Status "repair_required" `
            -Authenticated $false
    }

    throw
}

Write-Host "SUNSHINE_CREDENTIAL_PRESERVED=NO"
Write-Host "SUNSHINE_CREDENTIAL_ROTATED=YES"
Write-Host "SUNSHINE_AUTHENTICATED_API=PASS"
Write-Host "SECRET_STORAGE=LSA_PRIVATE_DATA"
Write-Host "PLAINTEXT_CONFIG_PASSWORD=ABSENT"
Write-Host "SECRET_VALUE_PRINTED=NO"
if ($sunshineServiceRestarted) {
    Write-Host "SUNSHINE_SERVICE_RESTARTED=YES"
}
else {
    Write-Host "SUNSHINE_SERVICE_RESTARTED=NO"
}

Write-Host "WINDOWS_REBOOT_REQUIRED=NO"
Write-Host "KG009D3_SUNSHINE_CREDENTIAL_CONFIGURATION=PASS"
