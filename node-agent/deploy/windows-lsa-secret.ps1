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

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern UInt32 LsaRetrievePrivateData(
        IntPtr PolicyHandle,
        ref LSA_UNICODE_STRING KeyName,
        out IntPtr PrivateData
    );

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaNtStatusToWinError(
        UInt32 Status
    );

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaClose(
        IntPtr PolicyHandle
    );

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaFreeMemory(
        IntPtr Buffer
    );

    private const UInt32 POLICY_GET_PRIVATE_INFORMATION = 0x00000004;
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

    private static IntPtr OpenPolicy(UInt32 access)
    {
        LSA_OBJECT_ATTRIBUTES attributes =
            new LSA_OBJECT_ATTRIBUTES();

        attributes.Length = 0;

        IntPtr policy;

        UInt32 status = LsaOpenPolicy(
            IntPtr.Zero,
            ref attributes,
            access,
            out policy
        );

        if (status != 0)
        {
            throw new InvalidOperationException(
                "LsaOpenPolicy failed: " +
                LsaNtStatusToWinError(status)
            );
        }

        return policy;
    }

    public static void Store(
        string secretName,
        string secretValue
    )
    {
        if (String.IsNullOrWhiteSpace(secretName))
            throw new ArgumentException(
                "LSA secret name cannot be blank."
            );

        if (secretValue == null)
            throw new ArgumentNullException("secretValue");

        IntPtr policy =
            OpenPolicy(POLICY_CREATE_SECRET);

        IntPtr nameBuffer = IntPtr.Zero;
        IntPtr dataBuffer = IntPtr.Zero;

        try
        {
            LSA_UNICODE_STRING name =
                InitString(secretName, out nameBuffer);

            LSA_UNICODE_STRING data =
                InitString(secretValue, out dataBuffer);

            UInt32 status = LsaStorePrivateData(
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

    public static string Retrieve(string secretName)
    {
        if (String.IsNullOrWhiteSpace(secretName))
            throw new ArgumentException(
                "LSA secret name cannot be blank."
            );

        IntPtr policy =
            OpenPolicy(POLICY_GET_PRIVATE_INFORMATION);

        IntPtr nameBuffer = IntPtr.Zero;
        IntPtr privateData = IntPtr.Zero;

        try
        {
            LSA_UNICODE_STRING name =
                InitString(secretName, out nameBuffer);

            UInt32 status = LsaRetrievePrivateData(
                policy,
                ref name,
                out privateData
            );

            if (status != 0)
            {
                UInt32 winError =
                    LsaNtStatusToWinError(status);

                // ERROR_FILE_NOT_FOUND / no such private-data name.
                if (winError == 2)
                    return null;

                throw new InvalidOperationException(
                    "LsaRetrievePrivateData failed: " +
                    winError
                );
            }

            if (privateData == IntPtr.Zero)
                return null;

            LSA_UNICODE_STRING data =
                (LSA_UNICODE_STRING)
                Marshal.PtrToStructure(
                    privateData,
                    typeof(LSA_UNICODE_STRING)
                );

            if (
                data.Buffer == IntPtr.Zero ||
                data.Length == 0
            )
            {
                return String.Empty;
            }

            return Marshal.PtrToStringUni(
                data.Buffer,
                data.Length / 2
            );
        }
        finally
        {
            if (privateData != IntPtr.Zero)
                LsaFreeMemory(privateData);

            if (nameBuffer != IntPtr.Zero)
                Marshal.FreeHGlobal(nameBuffer);

            if (policy != IntPtr.Zero)
                LsaClose(policy);
        }
    }

    public static void Delete(string secretName)
    {
        if (String.IsNullOrWhiteSpace(secretName))
            throw new ArgumentException(
                "LSA secret name cannot be blank."
            );

        IntPtr policy =
            OpenPolicy(POLICY_CREATE_SECRET);

        IntPtr nameBuffer = IntPtr.Zero;

        try
        {
            LSA_UNICODE_STRING name =
                InitString(secretName, out nameBuffer);

            UInt32 status = LsaStorePrivateDataNull(
                policy,
                ref name,
                IntPtr.Zero
            );

            if (status != 0)
            {
                UInt32 winError =
                    LsaNtStatusToWinError(status);

                if (winError != 2)
                {
                    throw new InvalidOperationException(
                        "Unable to delete LSA private secret: " +
                        winError
                    );
                }
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

    // Preserve the validated KG-009D2 public contract.
    public static void StoreDefaultPassword(string password)
    {
        Store("DefaultPassword", password);
    }

    public static void ClearDefaultPassword()
    {
        Delete("DefaultPassword");
    }
}
'@

if (-not ("KhanLsaSecret" -as [type])) {
    Add-Type `
        -TypeDefinition $LsaSource `
        -Language CSharp `
        -ErrorAction Stop
}
