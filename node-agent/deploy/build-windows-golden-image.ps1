param(
    [Parameter(Mandatory=$true)][ValidateSet("preflight","apply_windows","boot_files","finalize")][string]$Stage,
    [Parameter(Mandatory=$true)][string]$IsoPath,
    [Parameter(Mandatory=$true)][string]$OutputVhdx,
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$Edition = "Windows 11 Pro",
    [int]$DiskSizeGB = 80
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$MetaPath = Join-Path $Workspace "worker-state.json"
function Save-Meta($obj) { New-Item -ItemType Directory -Force -Path $Workspace | Out-Null; $obj | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $MetaPath }
function Load-Meta { if (!(Test-Path $MetaPath)) { throw "Worker metadata missing; run preflight first." }; Get-Content -Raw $MetaPath | ConvertFrom-Json }
function Dism-Apply([string]$ImageFile,[int]$Index,[string]$ApplyDir) {
    & dism.exe /Apply-Image /ImageFile:$ImageFile /Index:$Index /ApplyDir:$ApplyDir
    if ($LASTEXITCODE -ne 0) { throw "DISM Apply-Image failed with exit code $LASTEXITCODE" }
}
if ($Stage -eq "preflight") {
    if (!(Test-Path $IsoPath -PathType Leaf)) { throw "ISO not found: $IsoPath" }
    if (!(Get-Command Get-VHD -ErrorAction SilentlyContinue)) { throw "Hyper-V PowerShell module is unavailable." }
    New-Item -ItemType Directory -Force -Path $Workspace,(Split-Path $OutputVhdx -Parent) | Out-Null
    $disk = Mount-DiskImage -ImagePath $IsoPath -PassThru
    try {
        $vol = $disk | Get-Volume | Where-Object DriveLetter | Select-Object -First 1
        if (!$vol) { throw "Mounted ISO has no drive letter." }
        $install = @("$($vol.DriveLetter):\sources\install.wim","$($vol.DriveLetter):\sources\install.esd") | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (!$install) { throw "install.wim/install.esd not found in ISO." }
        $images = Get-WindowsImage -ImagePath $install
        $selected = $images | Where-Object ImageName -eq $Edition | Select-Object -First 1
        if (!$selected) { $selected = $images | Where-Object ImageName -match [regex]::Escape($Edition) | Select-Object -First 1 }
        if (!$selected) { throw "Requested Windows edition '$Edition' not found. Available: $($images.ImageName -join ', ')" }
        Save-Meta ([ordered]@{ IsoPath=$IsoPath; InstallRelative=$install.Substring(2); ImageIndex=[int]$selected.ImageIndex; ImageName=$selected.ImageName; OutputVhdx=$OutputVhdx; DiskSizeGB=$DiskSizeGB })
        Write-Host "PREFLIGHT_OK edition=$($selected.ImageName) index=$($selected.ImageIndex)"
    } finally { Dismount-DiskImage -ImagePath $IsoPath -ErrorAction SilentlyContinue }
    exit 0
}
$meta = Load-Meta
if ($Stage -eq "apply_windows") {
    if (Test-Path $OutputVhdx) { Remove-Item -Force $OutputVhdx }
    New-VHD -Path $OutputVhdx -Dynamic -SizeBytes ($DiskSizeGB * 1GB) | Out-Null
    $vhd = Mount-VHD -Path $OutputVhdx -PassThru
    try {
        $disk = $vhd | Get-Disk
        Initialize-Disk -Number $disk.Number -PartitionStyle GPT
        $efi = New-Partition -DiskNumber $disk.Number -Size 260MB -AssignDriveLetter
        Format-Volume -Partition $efi -FileSystem FAT32 -NewFileSystemLabel SYSTEM -Confirm:$false | Out-Null
        $os = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
        Format-Volume -Partition $os -FileSystem NTFS -NewFileSystemLabel WINDOWS -Confirm:$false | Out-Null
        $iso = Mount-DiskImage -ImagePath $IsoPath -PassThru
        try {
            $ivol = $iso | Get-Volume | Where-Object DriveLetter | Select-Object -First 1
            $install = "$($ivol.DriveLetter):$($meta.InstallRelative)"
            Dism-Apply $install ([int]$meta.ImageIndex) "$($os.DriveLetter):\"
        } finally { Dismount-DiskImage -ImagePath $IsoPath -ErrorAction SilentlyContinue }
        $meta | Add-Member -Force NoteProperty OsPartitionGuid $os.Guid.Guid
        $meta | Add-Member -Force NoteProperty EfiPartitionGuid $efi.Guid.Guid
        Save-Meta $meta
    } finally { Dismount-VHD -Path $OutputVhdx -ErrorAction SilentlyContinue }
    Write-Host "APPLY_WINDOWS_OK"
    exit 0
}
if ($Stage -eq "boot_files") {
    $vhd = Mount-VHD -Path $OutputVhdx -PassThru
    try {
        $disk = $vhd | Get-Disk
        $parts = Get-Partition -DiskNumber $disk.Number
        $efi = $parts | Where-Object GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' | Select-Object -First 1
        $os = $parts | Where-Object { $_.Type -eq 'Basic' -and $_.Size -gt 10GB } | Select-Object -First 1
        if (!$efi.DriveLetter) { $efi | Add-PartitionAccessPath -AssignDriveLetter; $efi = Get-Partition -DiskNumber $disk.Number -PartitionNumber $efi.PartitionNumber }
        if (!$os.DriveLetter) { $os | Add-PartitionAccessPath -AssignDriveLetter; $os = Get-Partition -DiskNumber $disk.Number -PartitionNumber $os.PartitionNumber }
        & bcdboot.exe "$($os.DriveLetter):\Windows" /s "$($efi.DriveLetter):" /f UEFI
        if ($LASTEXITCODE -ne 0) { throw "BCDBoot failed with exit code $LASTEXITCODE" }
    } finally { Dismount-VHD -Path $OutputVhdx -ErrorAction SilentlyContinue }
    Write-Host "BOOT_FILES_OK"
    exit 0
}
if ($Stage -eq "finalize") {
    $vhd = Get-VHD -Path $OutputVhdx
    if ($vhd.VhdType -ne 'Dynamic') { throw "Golden VHDX must be dynamic." }
    if ($vhd.Size -lt 40GB) { throw "Golden VHDX virtual size is unexpectedly small." }
    $ImageVersion = [System.IO.Path]::GetFileNameWithoutExtension($OutputVhdx)
    if ([string]::IsNullOrWhiteSpace($ImageVersion)) {
        throw "Unable to derive image version from VHDX path: $OutputVhdx"
    }
    $manifest = [ordered]@{ contract_version='kg008c-v1'; image_version=$ImageVersion; edition=$meta.ImageName; image_index=[int]$meta.ImageIndex; vhdx=$OutputVhdx; virtual_size=[int64]$vhd.Size; prepared_at=(Get-Date).ToUniversalTime().ToString('o'); generalized=$false }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Workspace 'golden-image-manifest.json')
    Write-Host "FINALIZE_OK vhdx=$OutputVhdx"
    exit 0
}
