param(
    [ValidateSet("Configure", "Validate")]
    [string]$Action = "Configure",

    [string]$SunshinePath = (
        "C:\Program Files\Sunshine\sunshine.exe"
    )
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity =
        [Security.Principal.WindowsIdentity]::GetCurrent()

    $principal =
        New-Object `
            Security.Principal.WindowsPrincipal($identity)

    if (
        -not $principal.IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator
        )
    ) {
        throw (
            "Sunshine application policy must run as Administrator."
        )
    }
}

function Get-SunshineAppsPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable
    )

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Sunshine executable is missing: $Executable"
    }

    $root =
        Split-Path `
            -Parent `
            $Executable

    $configDirectory =
        Join-Path `
            $root `
            "config"

    return (
        Join-Path `
            $configDirectory `
            "apps.json"
    )
}

function New-KhanCloudApplicationPolicy {
    return [ordered]@{
        env = [ordered]@{}
        apps = @(
            [ordered]@{
                name = "Khan Cloud Session"
                "image-path" = "desktop.png"
            }
        )
    }
}

function Test-KhanCloudApplicationPolicy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    try {
        $raw =
            Get-Content `
                -LiteralPath $Path `
                -Raw `
                -ErrorAction Stop

        $policy =
            $raw |
            ConvertFrom-Json `
                -ErrorAction Stop
    }
    catch {
        return $false
    }

    if ($null -eq $policy.apps) {
        return $false
    }

    $apps = @($policy.apps)

    if ($apps.Count -ne 1) {
        return $false
    }

    $app = $apps[0]

    if ([string]$app.name -ne "Khan Cloud Session") {
        return $false
    }

    $forbiddenProperties = @(
        "cmd",
        "detached",
        "prep-cmd",
        "auto-detach",
        "wait-all",
        "exit-timeout"
    )

    foreach ($property in $forbiddenProperties) {
        if (
            $null -ne (
                $app.PSObject.Properties[$property]
            )
        ) {
            return $false
        }
    }

    return $true
}

function Write-KhanCloudApplicationPolicy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $directory =
        Split-Path `
            -Parent `
            $Path

    New-Item `
        -ItemType Directory `
        -Path $directory `
        -Force |
        Out-Null

    $policy =
        New-KhanCloudApplicationPolicy

    $json =
        $policy |
        ConvertTo-Json `
            -Depth 10

    $utf8NoBom =
        New-Object `
            System.Text.UTF8Encoding($false)

    $temp =
        "$Path.khancloud.tmp"

    try {
        [System.IO.File]::WriteAllText(
            $temp,
            ($json + [Environment]::NewLine),
            $utf8NoBom
        )

        if (-not (Test-KhanCloudApplicationPolicy -Path $temp)) {
            throw (
                "Generated Sunshine application policy failed " +
                "validation."
            )
        }

        Move-Item `
            -LiteralPath $temp `
            -Destination $Path `
            -Force
    }
    finally {
        if (Test-Path -LiteralPath $temp) {
            Remove-Item `
                -LiteralPath $temp `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "============================================================"
Write-Host " KHAN CLOUD - SUNSHINE APPLICATION POLICY"
Write-Host "============================================================"

Assert-Administrator

$appsPath =
    Get-SunshineAppsPath `
        -Executable $SunshinePath

Write-Host ("SUNSHINE_APPS_PATH=" + $appsPath)

$alreadyCanonical =
    Test-KhanCloudApplicationPolicy `
        -Path $appsPath

if ($Action -eq "Validate") {
    if (-not $alreadyCanonical) {
        throw (
            "Sunshine application policy is not canonical."
        )
    }

    Write-Host "SUNSHINE_APP_POLICY=PASS"
    Write-Host "SUNSHINE_APP_POLICY_CHANGED=NO"
    Write-Host "SUNSHINE_STREAM_OWNER=KHAN_CLOUD_SESSION"
    Write-Host "SUNSHINE_LAUNCHER_OWNERSHIP=NONE"
    Write-Host "WINDOWS_REBOOT_REQUIRED=NO"
    Write-Host "Y44P_SUNSHINE_APP_POLICY_VALIDATION=PASS"
    exit 0
}

if ($alreadyCanonical) {
    Write-Host "SUNSHINE_APP_POLICY_ALREADY_CANONICAL=YES"
    Write-Host "SUNSHINE_APP_POLICY_CHANGED=NO"
}
else {
    Write-KhanCloudApplicationPolicy `
        -Path $appsPath

    if (-not (Test-KhanCloudApplicationPolicy -Path $appsPath)) {
        throw (
            "Sunshine application policy did not persist " +
            "canonically."
        )
    }

    Write-Host "SUNSHINE_APP_POLICY_ALREADY_CANONICAL=NO"
    Write-Host "SUNSHINE_APP_POLICY_CHANGED=YES"
}

Write-Host "SUNSHINE_APP_POLICY=PASS"
Write-Host "SUNSHINE_STREAM_OWNER=KHAN_CLOUD_SESSION"
Write-Host "SUNSHINE_LAUNCHER_OWNERSHIP=NONE"
Write-Host "SUNSHINE_SERVICE_RESTARTED=NO"
Write-Host "WINDOWS_REBOOT_REQUIRED=NO"
Write-Host "Y44P_SUNSHINE_APP_POLICY_CONFIGURATION=PASS"
