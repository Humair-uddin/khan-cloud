from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class ProtectedSecretError(RuntimeError):
    """Windows protected-secret retrieval failed."""


_POLICY_GET_PRIVATE_INFORMATION = 0x00000004


class _LsaUnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _LsaObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.c_void_p),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", ctypes.c_void_p),
        ("SecurityQualityOfService", ctypes.c_void_p),
    ]


def _ensure_windows() -> None:
    if os.name != "nt":
        raise ProtectedSecretError(
            "Windows LSA protected secrets are only available on Windows."
        )


def _lsa_string(value: str) -> tuple[_LsaUnicodeString, ctypes.Array]:
    buffer = ctypes.create_unicode_buffer(value)

    result = _LsaUnicodeString(
        Length=len(value.encode("utf-16-le")),
        MaximumLength=len(buffer) * 2,
        Buffer=ctypes.cast(buffer, wintypes.LPWSTR),
    )
    return result, buffer


def read_windows_protected_secret(
    secret_name: str,
    *,
    required: bool = True,
) -> str | None:
    """Read one LSA private-data value without persisting or logging it."""

    _ensure_windows()

    if not secret_name.strip():
        raise ProtectedSecretError(
            "Windows protected-secret name cannot be blank."
        )

    advapi32 = ctypes.WinDLL(
        "advapi32",
        use_last_error=True,
    )

    lsa_open_policy = advapi32.LsaOpenPolicy
    lsa_open_policy.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_LsaObjectAttributes),
        wintypes.ULONG,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    lsa_open_policy.restype = wintypes.ULONG

    lsa_retrieve = advapi32.LsaRetrievePrivateData
    lsa_retrieve.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_LsaUnicodeString),
        ctypes.POINTER(
            ctypes.POINTER(_LsaUnicodeString)
        ),
    ]
    lsa_retrieve.restype = wintypes.ULONG

    lsa_ntstatus_to_winerror = advapi32.LsaNtStatusToWinError
    lsa_ntstatus_to_winerror.argtypes = [wintypes.ULONG]
    lsa_ntstatus_to_winerror.restype = wintypes.ULONG

    lsa_close = advapi32.LsaClose
    lsa_close.argtypes = [wintypes.HANDLE]
    lsa_close.restype = wintypes.ULONG

    lsa_free_memory = advapi32.LsaFreeMemory
    lsa_free_memory.argtypes = [ctypes.c_void_p]
    lsa_free_memory.restype = wintypes.ULONG

    attributes = _LsaObjectAttributes()
    attributes.Length = 0

    policy = wintypes.HANDLE()

    status = lsa_open_policy(
        None,
        ctypes.byref(attributes),
        _POLICY_GET_PRIVATE_INFORMATION,
        ctypes.byref(policy),
    )

    if status != 0:
        error = int(
            lsa_ntstatus_to_winerror(status)
        )
        raise ProtectedSecretError(
            "Unable to open Windows LSA private-data policy "
            f"(error {error})."
        )

    private_data = ctypes.POINTER(
        _LsaUnicodeString
    )()

    # Keep the backing Unicode buffer referenced for the complete
    # native LSA call. The structure contains a pointer into this
    # ctypes allocation.
    name, name_buffer = _lsa_string(secret_name)

    try:
        status = lsa_retrieve(
            policy,
            ctypes.byref(name),
            ctypes.byref(private_data),
        )

        if status != 0:
            error = int(
                lsa_ntstatus_to_winerror(status)
            )

            if error == 2 and not required:
                return None

            if error == 2:
                raise ProtectedSecretError(
                    "Required Windows protected secret is absent."
                )

            raise ProtectedSecretError(
                "Unable to retrieve Windows protected secret "
                f"(error {error})."
            )

        if not private_data:
            if required:
                raise ProtectedSecretError(
                    "Required Windows protected secret is empty."
                )
            return None

        data = private_data.contents

        if not data.Buffer or data.Length == 0:
            if required:
                raise ProtectedSecretError(
                    "Required Windows protected secret is empty."
                )
            return None

        value = ctypes.wstring_at(
            data.Buffer,
            data.Length // 2,
        )

        if not value and required:
            raise ProtectedSecretError(
                "Required Windows protected secret is empty."
            )

        return value or None
    finally:
        if private_data:
            lsa_free_memory(
                ctypes.cast(
                    private_data,
                    ctypes.c_void_p,
                )
            )

        if policy:
            lsa_close(policy)
