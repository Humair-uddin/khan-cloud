param(
    [switch]$Generalize,
    [string]$ManifestPath = "C:\ProgramData\KhanCloud\Template\manifest.json"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Windows gaming template preparation must run as Administrator."
    }
}

function Require-Path {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path)) { throw "$Label missing: $Path" }
}

Write-Host "============================================================"
Write-Host " KHAN CLOUD — WINDOWS GAMING GOLDEN TEMPLATE PREP"
Write-Host "============================================================"

Assert-Administrator

$AgentRoot = "C:\ProgramData\KhanCloud\Agent"
$Runtime = Join-Path $AgentRoot "runtime"
$Config = Join-Path $AgentRoot "config.yaml"
$Credentials = Join-Path $AgentRoot "credentials.json"
$Identity = Join-Path $AgentRoot "identity.json"
$Python = Join-Path $Runtime ".venv\Scripts\python.exe"
$SunshineCandidates = @(
    "C:\Program Files\Sunshine\sunshine.exe",
    "C:\Program Files\Sunshine\sunshine.EXE"
)

Write-Host "`n===== REQUIRED COMPONENTS ====="
Require-Path $Runtime "KhanCloud runtime"
Require-Path $Config "KhanCloud config"
Require-Path $Python "KhanCloud Python"

$Sunshine = $SunshineCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
if (-not $Sunshine) { throw "Sunshine executable is not installed in the golden image." }
Write-Host "SUNSHINE: $Sunshine"

$qga = Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue
if (-not $qga) { $qga = Get-Service | Where-Object { $_.DisplayName -match 'QEMU Guest Agent' } | Select-Object -First 1 }
if (-not $qga) { throw "QEMU Guest Agent service is not installed." }
Write-Host "QGA_SERVICE: $($qga.Name)"

$agent = Get-Service -Name "KhanCloudAgent" -ErrorAction Stop
Write-Host "AGENT_SERVICE: $($agent.Name)"

Write-Host "`n===== VALIDATE RUNTIME ====="
& $Python -m compileall -q (Join-Path $Runtime "khan_agent")
if ($LASTEXITCODE -ne 0) { throw "KhanCloud runtime compile validation failed." }

Write-Host "`n===== SCRUB CLONE-SPECIFIC IDENTITY ====="
Stop-Service KhanCloudAgent -Force -ErrorAction SilentlyContinue
Set-Service KhanCloudAgent -StartupType Manual

foreach ($Path in @($Credentials, $Identity)) {
    if (Test-Path $Path -PathType Leaf) {
        Remove-Item $Path -Force
        Write-Host "REMOVED: $Path"
    }
}

$raw = Get-Content -Raw -Path $Config
if ($raw -notmatch '(?m)^\s*deployment_enrollment_code:') { throw "deployment_enrollment_code key missing from config." }
if ($raw -notmatch '(?m)^\s*control_plane_url:') { throw "control_plane_url key missing from config." }
$raw = [regex]::Replace($raw, '(?m)^(\s*deployment_enrollment_code:)\s*.*$', '$1 ""')
$raw = [regex]::Replace($raw, '(?m)^(\s*control_plane_url:)\s*.*$', '$1 ""')
Set-Content -Path $Config -Value $raw -Encoding UTF8

Write-Host "`n===== CLEAR MACHINE-SPECIFIC TRANSIENT STATE ====="
$Transient = @(
    "C:\ProgramData\KhanCloud\Bootstrap\bootstrap.checkpoints",
    "C:\ProgramData\KhanCloud\Agent\runtime-state.json"
)
foreach ($Path in $Transient) {
    if (Test-Path $Path) { Remove-Item $Path -Force -ErrorAction SilentlyContinue }
}

$TemplateRoot = Split-Path $ManifestPath -Parent
New-Item -ItemType Directory -Path $TemplateRoot -Force | Out-Null

$manifest = [ordered]@{
    contract_version = "kg006-v1"
    prepared = $true
    prepared_at_utc = [DateTime]::UtcNow.ToString("o")
    qemu_guest_agent = $qga.Name
    khan_agent_runtime = $Runtime
    khan_agent_service = "KhanCloudAgent"
    sunshine_executable = $Sunshine
    clone_identity_scrubbed = (-not (Test-Path $Credentials)) -and (-not (Test-Path $Identity))
    enrollment_placeholder_blank = $true
    control_plane_placeholder_blank = $true
    agent_startup = "Manual"
    generalize_requested = [bool]$Generalize
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $ManifestPath -Encoding UTF8
Write-Host "MANIFEST: $ManifestPath"

Write-Host "`n===== FINAL VALIDATION ====="
& (Join-Path $PSScriptRoot "validate-windows-gaming-template.ps1") -ManifestPath $ManifestPath
if ($LASTEXITCODE -ne 0) { throw "Golden template validation failed." }

if ($Generalize) {
    Write-Host "`n===== SYSPREP GENERALIZE / SHUTDOWN ====="
    $Sysprep = "$env:WINDIR\System32\Sysprep\Sysprep.exe"
    Require-Path $Sysprep "Sysprep"
    Start-Process -FilePath $Sysprep -ArgumentList "/generalize /oobe /shutdown /quiet" -Wait
    exit 0
}

Write-Host "`nPASS — template prepared. Validate, then seal it on Proxmox."
Write-Host "Use -Generalize only when ready for the final Sysprep shutdown."
