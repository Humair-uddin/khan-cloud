from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

CPP = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.cpp"
)


def source():
    return CPP.read_text()


def gpu_block():
    text = source()

    marker = text.index(
        "KhanFrameHandoffSecurityDescriptor"
    )

    return text[
        max(0, marker - 1800):
        min(len(text), marker + 6500)
    ]


def test_global_frame_resource_namespace():
    text = source()

    assert (
        'L"Global\\\\KhanCloud.VDD.Frame."'
        in text
    )

    assert (
        'L"Local\\\\KhanCloud.VDD.Frame."'
        not in text
    )


def test_nt_handle_and_keyed_mutex_preserved():
    text = source()

    assert (
        "D3D11_RESOURCE_MISC_SHARED_NTHANDLE"
        in text
    )

    assert (
        "D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX"
        in text
    )


def test_gpu_resource_has_explicit_security_attributes():
    block = gpu_block()

    assert (
        "SECURITY_ATTRIBUTES frameSecurityAttributes"
        in block
    )

    assert (
        "&frameSecurityAttributes"
        in block
    )


def test_gpu_acl_is_system_and_administrators_only():
    block = gpu_block()

    assert (
        'L"D:P(A;;GA;;;SY)(A;;GA;;;BA)"'
        in block
    )

    assert ";;;WD)" not in block


def test_gpu_resource_access_flags_preserved():
    block = gpu_block()

    assert "DXGI_SHARED_RESOURCE_READ" in block
    assert "DXGI_SHARED_RESOURCE_WRITE" in block


def test_gpu_security_descriptor_is_released():
    block = gpu_block()

    assert "LocalFree(" in block


def test_no_world_acl_anywhere():
    text = source()

    descriptors = re.findall(
        r'L"(D:[^"]+)"',
        text,
    )

    assert descriptors

    assert not any(
        ";;;WD)" in value
        for value in descriptors
    )


def test_at_least_one_system_admin_acl_exists():
    text = source()

    descriptors = re.findall(
        r'L"(D:[^"]+)"',
        text,
    )

    assert any(
        ";;;SY)" in value
        and ";;;BA)" in value
        and ";;;WD)" not in value
        for value in descriptors
    )
