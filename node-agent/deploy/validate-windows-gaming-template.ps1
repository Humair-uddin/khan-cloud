param(
    [string]$ManifestPath = "C:\ProgramData\KhanCloud\Template\manifest.json",
    [switch]$JsonOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$AgentRoot = "C:\ProgramData\KhanCloud\Agent"
$Runtime = Join-Path $AgentRoot "runtime"
$Config = Join-Path $AgentRoot "config.yaml"
$Credentials = Join-Path $AgentRoot "credentials.json"
$Identity = Join-Path $AgentRoot "identity.json"
$BrokerState = Join-Path $AgentRoot "session-broker.json"
$BrokerConfigurator = Join-Path `
    $Runtime `
    "deploy\configure-windows-gaming-session.ps1"
$Python = Join-Path $Runtime ".venv\Scripts\python.exe"

$checks = [ordered]@{}
$checks.contract_version = "kg006-v1"
$checks.runtime_present = Test-Path $Runtime -PathType Container
$checks.python_present = Test-Path $Python -PathType Leaf
$checks.config_present = Test-Path $Config -PathType Leaf
$checks.credentials_absent = -not (Test-Path $Credentials)
$checks.identity_absent = -not (Test-Path $Identity)
$checks.session_broker_capability_present = (
    Test-Path $BrokerConfigurator -PathType Leaf
)
$checks.session_broker_state_absent = (
    -not (Test-Path $BrokerState)
)

$agent = Get-Service -Name "KhanCloudAgent" -ErrorAction SilentlyContinue
$checks.agent_service_present = [bool]$agent
$checks.agent_not_running = [bool]$agent -and $agent.Status -ne "Running"

$qga = Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue
if (-not $qga) { $qga = Get-Service | Where-Object { $_.DisplayName -match 'QEMU Guest Agent' } | Select-Object -First 1 }
$checks.qga_present = [bool]$qga

$Sunshine = @(
    "C:\Program Files\Sunshine\sunshine.exe",
    "C:\Program Files\Sunshine\sunshine.EXE"
) | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
$checks.sunshine_present = [bool]$Sunshine

if ($checks.config_present) {
    $raw = Get-Content -Raw -Path $Config
    $enrollment = [regex]::Match($raw, '(?m)^\s*deployment_enrollment_code:\s*["'']?([^"''\r\n]*)').Groups[1].Value.Trim()
    $url = [regex]::Match($raw, '(?m)^\s*control_plane_url:\s*["'']?([^"''\r\n]*)').Groups[1].Value.Trim()
    $checks.enrollment_placeholder_blank = ($enrollment -eq "")
    $checks.control_plane_placeholder_blank = ($url -eq "")
} else {
    $checks.enrollment_placeholder_blank = $false
    $checks.control_plane_placeholder_blank = $false
}

if (Test-Path $ManifestPath -PathType Leaf) {
    try { $manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json }
    catch { throw "Template manifest is invalid JSON." }
    $checks.manifest_present = $true
    $checks.manifest_contract_valid = ($manifest.contract_version -eq "kg006-v1" -and [bool]$manifest.prepared)
} else {
    $checks.manifest_present = $false
    $checks.manifest_contract_valid = $false
}

$failed = @($checks.GetEnumerator() | Where-Object { $_.Key -ne 'contract_version' -and -not [bool]$_.Value })
$result = [ordered]@{
    contract_version = "kg006-v1"
    valid = ($failed.Count -eq 0)
    failed_checks = @($failed | ForEach-Object { $_.Key })
    checks = $checks
    sunshine_executable = if ($Sunshine) { $Sunshine } else { "" }
}

if ($JsonOnly) {
    $result | ConvertTo-Json -Depth 8 -Compress
} else {
    $result | ConvertTo-Json -Depth 8
}

if (-not $result.valid) { exit 2 }
exit 0
