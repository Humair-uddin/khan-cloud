param(
    [ValidateSet("Configure", "Deconfigure")]
    [string]$Action = "Configure",

    [string]$UserName = "KhanGaming",

    [string]$StatePath = (
        Join-Path $env:ProgramData `
            "KhanCloud\Agent\session-broker.json"
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
            "Windows gaming session configuration " +
            "must run as Administrator."
        )
    }
}

function New-RandomPassword {
    param([int]$Bytes = 48)

    $buffer = New-Object byte[] $Bytes

    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()

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

$LsaSource = @'
using System;
using System.Runtime.InteropServices;

public static class KhanLsaSecret
{
    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_UNICODE_STRING
    {
        public UInt16 Length;
        public UInt16 MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_OBJECT_ATTRIBUTES
    {
        public UInt32 Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public UInt32 Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern UInt32 LsaOpenPolicy(
        IntPtr SystemName,
        ref LSA_OBJECT_ATTRIBUTES ObjectAttributes,
        UInt32 DesiredAccess,
        out IntPtr PolicyHandle
    );

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern UInt32 LsaStorePrivateData(
        IntPtr PolicyHandle,
        ref LSA_UNICODE_STRING KeyName,
        ref LSA_UNICODE_STRING PrivateData
    );

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaNtStatusToWinError(
        UInt32 Status
    );

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaClose(
        IntPtr PolicyHandle
    );

    private const UInt32 POLICY_CREATE_SECRET = 0x00000020;

    private static LSA_UNICODE_STRING InitString(
        string value,
        out IntPtr buffer
    )
    {
        buffer = Marshal.StringToHGlobalUni(value);

        return new LSA_UNICODE_STRING {
            Buffer = buffer,
            Length = (UInt16)(value.Length * 2),
            MaximumLength = (UInt16)((value.Length + 1) * 2)
        };
    }

    [DllImport(
        "advapi32.dll",
        EntryPoint = "LsaStorePrivateData",
        SetLastError = true
    )]
    private static extern UInt32 LsaStorePrivateDataNull(
        IntPtr PolicyHandle,
        ref LSA_UNICODE_STRING KeyName,
        IntPtr PrivateData
    );

    public static void StoreDefaultPassword(string password)
    {
        LSA_OBJECT_ATTRIBUTES attributes =
            new LSA_OBJECT_ATTRIBUTES();

        attributes.Length = 0;

        IntPtr policy;

        UInt32 status = LsaOpenPolicy(
            IntPtr.Zero,
            ref attributes,
            POLICY_CREATE_SECRET,
            out policy
        );

        if (status != 0)
        {
            throw new InvalidOperationException(
                "LsaOpenPolicy failed: " +
                LsaNtStatusToWinError(status)
            );
        }

        IntPtr nameBuffer = IntPtr.Zero;
        IntPtr dataBuffer = IntPtr.Zero;

        try
        {
            LSA_UNICODE_STRING name =
                InitString("DefaultPassword", out nameBuffer);

            LSA_UNICODE_STRING data =
                InitString(password, out dataBuffer);

            status = LsaStorePrivateData(
                policy,
                ref name,
                ref data
            );

            if (status != 0)
            {
                throw new InvalidOperationException(
                    "LsaStorePrivateData failed: " +
                    LsaNtStatusToWinError(status)
                );
            }
        }
        finally
        {
            if (nameBuffer != IntPtr.Zero)
                Marshal.FreeHGlobal(nameBuffer);

            if (dataBuffer != IntPtr.Zero)
                Marshal.FreeHGlobal(dataBuffer);

            if (policy != IntPtr.Zero)
                LsaClose(policy);
        }
    }

    public static void ClearDefaultPassword()
    {
        LSA_OBJECT_ATTRIBUTES attributes =
            new LSA_OBJECT_ATTRIBUTES();

        attributes.Length = 0;

        IntPtr policy;

        UInt32 status = LsaOpenPolicy(
            IntPtr.Zero,
            ref attributes,
            POLICY_CREATE_SECRET,
            out policy
        );

        if (status != 0)
        {
            throw new InvalidOperationException(
                "LsaOpenPolicy failed: " +
                LsaNtStatusToWinError(status)
            );
        }

        IntPtr nameBuffer = IntPtr.Zero;

        try
        {
            LSA_UNICODE_STRING name =
                InitString("DefaultPassword", out nameBuffer);

            status = LsaStorePrivateDataNull(
                policy,
                ref name,
                IntPtr.Zero
            );

            if (status != 0)
            {
                throw new InvalidOperationException(
                    "Unable to delete LSA DefaultPassword secret: " +
                    LsaNtStatusToWinError(status)
                );
            }
        }
        finally
        {
            if (nameBuffer != IntPtr.Zero)
                Marshal.FreeHGlobal(nameBuffer);

            if (policy != IntPtr.Zero)
                LsaClose(policy);
        }
    }
}
'@

Write-Host "============================================================"
Write-Host " KHAN CLOUD - MANAGED WINDOWS GAMING SESSION"
Write-Host "============================================================"

Assert-Administrator

if ([string]::IsNullOrWhiteSpace($UserName)) {
    throw "Managed gaming username cannot be blank."
}

$invalidUserNameChars = @(
    [char]92,
    [char]47,
    [char]64,
    [char]34
)

if (
    $UserName.IndexOfAny(
        [char[]]$invalidUserNameChars
    ) -ge 0
) {
    throw "Managed gaming username contains invalid characters."
}

Add-Type -TypeDefinition $LsaSource -Language CSharp

$StateParent = Split-Path $StatePath -Parent
$AccountStatePath = Join-Path `
    $StateParent `
    "session-broker-account.json"

New-Item `
    -ItemType Directory `
    -Path $StateParent `
    -Force |
    Out-Null

$existingState = $null

if (Test-Path $StatePath -PathType Leaf) {
    try {
        $existingState = (
            Get-Content -Raw $StatePath |
            ConvertFrom-Json
        )
    }
    catch {
        throw "Existing session-broker state is invalid."
    }
}

$stateIsOwned = $false

if ($existingState) {
    $stateIsOwned = (
        $existingState.contract_version -eq "kg009d2-v1" -and
        $existingState.mode -eq "managed_autologon" -and
        $existingState.managed -eq $true -and
        -not [string]::IsNullOrWhiteSpace(
            [string]$existingState.username
        )
    )

    if (-not $stateIsOwned) {
        throw (
            "Existing session-broker state is not a valid " +
            "Khan Cloud managed-session ownership contract."
        )
    }
}

$accountState = $null
$accountIsOwned = $false

if (Test-Path $AccountStatePath -PathType Leaf) {
    try {
        $accountState = (
            Get-Content -Raw $AccountStatePath |
            ConvertFrom-Json
        )
    }
    catch {
        throw "Existing managed-account ownership state is invalid."
    }

    $accountIsOwned = (
        $accountState.contract_version -eq "kg009d2-account-v1" -and
        $accountState.managed_account -eq $true -and
        -not [string]::IsNullOrWhiteSpace(
            [string]$accountState.username
        )
    )

    if (-not $accountIsOwned) {
        throw (
            "Existing managed-account ownership state is not a valid " +
            "Khan Cloud account ownership contract."
        )
    }

    if ($accountState.username -ne $UserName) {
        throw (
            "Khan Cloud managed-account ownership marker belongs to " +
            "a different account: " +
            $accountState.username
        )
    }
}

$account = Get-LocalUser `
    -Name $UserName `
    -ErrorAction SilentlyContinue

if (
    $Action -eq "Configure" -and
    $account -and
    -not $stateIsOwned -and
    -not $accountIsOwned
) {
    throw (
        "Refusing to take ownership of an existing local account " +
        "without valid Khan Cloud account ownership state: $UserName"
    )
}

if (
    $accountIsOwned -and
    -not $account
) {
    throw (
        "Khan Cloud account ownership state exists but the managed " +
        "local account is missing: $UserName"
    )
}

if (
    $stateIsOwned -and
    $existingState.username -ne $UserName
) {
    throw (
        "Existing Khan Cloud broker owns a different account: " +
        $existingState.username
    )
}

$Winlogon = (
    "HKLM:\SOFTWARE\Microsoft\Windows NT\" +
    "CurrentVersion\Winlogon"
)

if ($Action -eq "Deconfigure") {
    if (-not $stateIsOwned) {
        if (Test-Path $StatePath -PathType Leaf) {
            throw (
                "Refusing to deconfigure an unowned Windows " +
                "gaming-session broker state."
            )
        }

        Write-Host "BROKER_STATE=ABSENT"
        Write-Host "AUTOADMINLOGON=UNCHANGED"
        Write-Host "KG009D2_MANAGED_SESSION_DECONFIGURATION=NOOP"
        exit 0
    }

    $ownedUser = [string]$existingState.username

    $currentAutoUser = [string](
        Get-ItemPropertyValue `
            -Path $Winlogon `
            -Name "DefaultUserName" `
            -ErrorAction SilentlyContinue
    )

    $currentAutoDomain = [string](
        Get-ItemPropertyValue `
            -Path $Winlogon `
            -Name "DefaultDomainName" `
            -ErrorAction SilentlyContinue
    )

    $ownsWinlogon = (
        $currentAutoUser -eq $ownedUser -and
        (
            [string]::IsNullOrWhiteSpace($currentAutoDomain) -or
            $currentAutoDomain -eq [string]$existingState.domain
        )
    )

    if ($ownsWinlogon) {
        Set-ItemProperty `
            -Path $Winlogon `
            -Name "AutoAdminLogon" `
            -Type String `
            -Value "0"

        foreach ($name in @(
            "DefaultUserName",
            "DefaultDomainName",
            "DefaultPassword",
            "AutoLogonCount"
        )) {
            Remove-ItemProperty `
                -Path $Winlogon `
                -Name $name `
                -ErrorAction SilentlyContinue
        }

        [KhanLsaSecret]::ClearDefaultPassword()

        Write-Host "AUTOADMINLOGON=DISABLED"
        Write-Host "LSA_DEFAULTPASSWORD=REMOVED"
    }
    else {
        throw (
            "Refusing to modify Winlogon because it is no longer " +
            "owned by the Khan Cloud managed gaming account."
        )
    }

    Remove-Item `
        -Path $StatePath `
        -Force `
        -ErrorAction Stop

    Write-Host "BROKER_STATE=REMOVED"
    Write-Host "ACCOUNT_PRESERVED=$ownedUser"

    if (Test-Path $AccountStatePath -PathType Leaf) {
        Write-Host "ACCOUNT_OWNERSHIP_STATE=PRESERVED"
    }
    else {
        throw (
            "Managed account ownership marker is missing during " +
            "deconfiguration."
        )
    }

    Write-Host "KG009D2_MANAGED_SESSION_DECONFIGURATION=PASS"
    exit 0
}

$passwordText = New-RandomPassword
$password = ConvertTo-SecureString `
    $passwordText `
    -AsPlainText `
    -Force

if (-not $account) {
    New-LocalUser `
        -Name $UserName `
        -Password $password `
        -AccountNeverExpires `
        -PasswordNeverExpires `
        -UserMayNotChangePassword `
        -Description "Khan Cloud managed gaming desktop account" |
        Out-Null

    $accountOwnership = [ordered]@{
        contract_version = "kg009d2-account-v1"
        managed_account = $true
        username = $UserName
        domain = $env:COMPUTERNAME
    }

    $accountOwnershipTemp = "$AccountStatePath.tmp"

    $accountOwnership |
        ConvertTo-Json -Depth 4 |
        Set-Content `
            -Path $accountOwnershipTemp `
            -Encoding ASCII `
            -Force

    Move-Item `
        -Path $accountOwnershipTemp `
        -Destination $AccountStatePath `
        -Force

    Write-Host "ACCOUNT_CREATED=$UserName"
    Write-Host "ACCOUNT_OWNERSHIP_STATE=$AccountStatePath"
}
else {
    Set-LocalUser `
        -Name $UserName `
        -Password $password

    Write-Host "ACCOUNT_ROTATED=$UserName"
}

$admins = Get-LocalGroupMember `
    -Group "Administrators" `
    -ErrorAction SilentlyContinue

$adminMatch = @(
    $admins |
    Where-Object {
        $_.Name.EndsWith(
            ([char]92 + $UserName),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
)

if ($adminMatch.Count -gt 0) {
    throw (
        "Managed gaming account must not be a local administrator."
    )
}

[KhanLsaSecret]::StoreDefaultPassword(
    $passwordText
)

# Remove plaintext fallback before enabling autologon.
Remove-ItemProperty `
    -Path $Winlogon `
    -Name "DefaultPassword" `
    -ErrorAction SilentlyContinue

Set-ItemProperty `
    -Path $Winlogon `
    -Name "DefaultUserName" `
    -Type String `
    -Value $UserName

Set-ItemProperty `
    -Path $Winlogon `
    -Name "DefaultDomainName" `
    -Type String `
    -Value $env:COMPUTERNAME

Set-ItemProperty `
    -Path $Winlogon `
    -Name "AutoAdminLogon" `
    -Type String `
    -Value "1"

# Do not allow an old finite AutoLogonCount to silently disable
# the managed desktop on a later boot.
Remove-ItemProperty `
    -Path $Winlogon `
    -Name "AutoLogonCount" `
    -ErrorAction SilentlyContinue

$state = [ordered]@{
    contract_version = "kg009d2-v1"
    mode = "managed_autologon"
    managed = $true
    username = $UserName
    domain = $env:COMPUTERNAME
    secret_store = "lsa_private_data"
    plaintext_registry_password = $false
    configured_at_utc = (
        [DateTime]::UtcNow.ToString("o")
    )
}

$temp = "$StatePath.tmp"

$state |
    ConvertTo-Json -Depth 5 |
    Set-Content `
        -Path $temp `
        -Encoding UTF8

Move-Item `
    -Path $temp `
    -Destination $StatePath `
    -Force

$password = $null
$passwordText = $null

[GC]::Collect()
[GC]::WaitForPendingFinalizers()

Write-Host "BROKER_STATE=$StatePath"
Write-Host "AUTOADMINLOGON=ENABLED"
Write-Host "PASSWORD_STORAGE=LSA_PRIVATE_DATA"
Write-Host "PLAINTEXT_DEFAULTPASSWORD=ABSENT"
Write-Host "REBOOT_REQUIRED_FOR_NEW_CONSOLE_SESSION=YES"
Write-Host "KG009D2_MANAGED_SESSION_CONFIGURATION=PASS"
