from pathlib import Path

from app.main import FRONTEND_DIR, app


def test_frontend_directory_exists() -> None:
    assert FRONTEND_DIR == Path(__file__).resolve().parents[2] / "frontend"
    assert (FRONTEND_DIR / "index.html").is_file()
    assert (FRONTEND_DIR / "src" / "app.js").is_file()


def test_control_plane_ui_is_mounted() -> None:
    mount_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/ui" in mount_paths
