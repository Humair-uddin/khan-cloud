from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "package_vdd.py"


def load_packager():
    spec = importlib.util.spec_from_file_location(
        "khan_vdd_packager",
        PACKAGER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_build(tmp_path: Path, settings: str | None = None) -> Path:
    build = tmp_path / "KhanVirtualDisplay"
    runtime = build / "RuntimeConfig"
    edid = runtime / "EDID"

    edid.mkdir(parents=True)

    for name in (
        "KhanVirtualDisplay.inf",
        "KhanVirtualDisplay.dll",
        "KhanVirtualDisplay.cat",
    ):
        (build / name).write_bytes(("artifact:" + name).encode())

    if settings is None:
        settings = """<?xml version="1.0"?>
<settings>
  <resolutions>
    <resolution>
      <width>1920</width>
      <height>1080</height>
      <refresh_rate>60</refresh_rate>
    </resolution>
    <resolution>
      <width>2560</width>
      <height>1440</height>
      <refresh_rate>120</refresh_rate>
    </resolution>
  </resolutions>
</settings>
"""

    (runtime / "khan-vdd-settings.xml").write_text(
        settings,
        encoding="utf-8",
    )
    (edid / "monitor_profile.xml").write_text(
        "<monitor/>",
        encoding="utf-8",
    )

    return build


def test_packager_is_version_controlled_source():
    assert PACKAGER.is_file()


def test_package_contains_driver_and_runtime_contract(tmp_path):
    pkg = load_packager()
    build = make_build(tmp_path)
    output = tmp_path / "vdd.zip"

    result = pkg.write_package(build, output)

    assert result["runtime_config_required"] is True
    assert result["runtime_mode_count"] == 2

    with zipfile.ZipFile(output) as z:
        names = set(z.namelist())

        assert (
            "KhanVirtualDisplay/KhanVirtualDisplay.inf"
            in names
        )
        assert (
            "KhanVirtualDisplay/KhanVirtualDisplay.dll"
            in names
        )
        assert (
            "KhanVirtualDisplay/KhanVirtualDisplay.cat"
            in names
        )
        assert (
            "KhanVirtualDisplay/RuntimeConfig/"
            "khan-vdd-settings.xml"
            in names
        )
        assert (
            "KhanVirtualDisplay/RuntimeConfig/EDID/"
            "monitor_profile.xml"
            in names
        )
        assert (
            "KhanVirtualDisplay/package-manifest.json"
            in names
        )

        manifest = json.loads(
            z.read(
                "KhanVirtualDisplay/package-manifest.json"
            )
        )

    assert manifest["schema"] == "khan-cloud-vdd-package-v1"
    assert manifest["runtime_config_required"] is True
    assert manifest["runtime_mode_count"] == 2


def test_packager_refuses_missing_runtime_settings(tmp_path):
    pkg = load_packager()
    build = make_build(tmp_path)
    (build / "RuntimeConfig/khan-vdd-settings.xml").unlink()

    with pytest.raises(pkg.PackageError):
        pkg.write_package(build, tmp_path / "bad.zip")


def test_packager_refuses_missing_edid_profile(tmp_path):
    pkg = load_packager()
    build = make_build(tmp_path)
    (build / "RuntimeConfig/EDID/monitor_profile.xml").unlink()

    with pytest.raises(pkg.PackageError):
        pkg.write_package(build, tmp_path / "bad.zip")


def test_packager_refuses_missing_driver_artifact(tmp_path):
    pkg = load_packager()
    build = make_build(tmp_path)
    (build / "KhanVirtualDisplay.dll").unlink()

    with pytest.raises(pkg.PackageError):
        pkg.write_package(build, tmp_path / "bad.zip")


def test_packager_refuses_empty_runtime_mode_policy(tmp_path):
    pkg = load_packager()

    build = make_build(
        tmp_path,
        """<?xml version="1.0"?>
<settings>
  <resolutions/>
</settings>
""",
    )

    with pytest.raises(pkg.PackageError):
        pkg.write_package(build, tmp_path / "bad.zip")


def test_packager_refuses_duplicate_runtime_modes(tmp_path):
    pkg = load_packager()

    build = make_build(
        tmp_path,
        """<?xml version="1.0"?>
<settings>
  <resolutions>
    <resolution>
      <width>1920</width>
      <height>1080</height>
      <refresh_rate>60</refresh_rate>
    </resolution>
    <resolution>
      <width>1920</width>
      <height>1080</height>
      <refresh_rate>60</refresh_rate>
    </resolution>
  </resolutions>
</settings>
""",
    )

    with pytest.raises(pkg.PackageError):
        pkg.write_package(build, tmp_path / "bad.zip")
