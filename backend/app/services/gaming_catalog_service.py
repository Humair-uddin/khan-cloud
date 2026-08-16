from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import NodeCapacity
from app.models.gaming_catalog import (
    GamingTitle,
    NodeGameInventory,
    NodeGameQualification,
)
from app.models.node import Node


QUALIFICATION_MAX_AGE = timedelta(minutes=5)


def ensure_builtin_titles(db: Session) -> None:
    existing = db.scalar(
        select(GamingTitle).where(
            GamingTitle.slug == "counter-strike-2"
        )
    )
    if existing is None:
        db.add(
            GamingTitle(
                slug="counter-strike-2",
                name="Counter-Strike 2",
                launcher="steam",
                launcher_app_id="730",
                platform="windows",
                minimum_vram_mb=8192,
                minimum_memory_mb=8192,
                minimum_cpu_threads=4,
                minimum_storage_mb=0,
                streaming_backend="sunshine",
                qualification_policy_version="kg001-v1",
                metadata_json={"acceptance_title": True},
            )
        )
        db.flush()


def _gpu_vram_values_mb(node: Node) -> list[int]:
    inv = node.inventory or {}
    gpu = inv.get("gpu") or inv.get("nvidia") or {}
    devices = gpu.get("gpus", []) if isinstance(gpu, dict) else []

    if not devices:
        devices = inv.get("gpus", [])

    values: list[int] = []

    for device in devices:
        if not isinstance(device, dict):
            continue

        raw = device.get(
            "memory_total_mib",
            device.get(
                "vram_mb",
                device.get("memory_mb", 0),
            ),
        )

        try:
            values.append(int(raw or 0))
        except (TypeError, ValueError):
            values.append(0)

    return values


def _maximum_gpu_vram_mb(node: Node) -> int:
    values = _gpu_vram_values_mb(node)
    return max(values, default=0)


def _memory_mb(node: Node) -> int:
    inv = node.inventory or {}
    raw = (inv.get("memory") or {}).get(
        "total_bytes",
        node.memory_total_bytes or 0,
    )

    try:
        return int(raw or 0) // (1024 * 1024)
    except (TypeError, ValueError):
        return 0


def _cpu_threads(node: Node) -> int:
    inv = node.inventory or {}
    raw = (inv.get("cpu") or {}).get(
        "logical_count",
        node.cpu_logical_count or 0,
    )

    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _storage_available_mb(
    db: Session,
    node: Node,
) -> int:
    capacity = db.scalar(
        select(NodeCapacity).where(
            NodeCapacity.node_id == node.id
        )
    )

    if capacity is not None:
        available = max(
            0,
            int(capacity.storage_allocatable_bytes or 0)
            - int(capacity.storage_allocated_bytes or 0),
        )
        return available // (1024 * 1024)

    filesystem = (node.inventory or {}).get("filesystem") or {}

    try:
        return int(
            filesystem.get("root_free_bytes") or 0
        ) // (1024 * 1024)
    except (TypeError, ValueError):
        return 0


def _sunshine_ready(node: Node) -> bool:
    gaming = (node.inventory or {}).get("gaming") or {}
    sunshine = (gaming.get("streaming") or {}).get(
        "sunshine"
    ) or {}

    return bool(
        sunshine.get("installed")
        and sunshine.get("ready")
    )


def qualification_is_fresh(
    qualification: NodeGameQualification,
    *,
    now: datetime | None = None,
) -> bool:
    if qualification.evaluated_at is None:
        return False

    reference = now or datetime.now(UTC)
    evaluated_at = qualification.evaluated_at

    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=UTC)

    age = reference - evaluated_at

    return (
        age >= timedelta(0)
        and age <= QUALIFICATION_MAX_AGE
    )


def qualify_node_game(
    db: Session,
    *,
    node: Node,
    title: GamingTitle,
    installation: NodeGameInventory,
    evaluated_at: datetime,
) -> None:
    reasons: list[str] = []

    maximum_vram_mb = _maximum_gpu_vram_mb(node)
    memory_mb = _memory_mb(node)
    cpu_threads = _cpu_threads(node)
    storage_available_mb = _storage_available_mb(db, node)
    sunshine_ready = _sunshine_ready(node)

    if installation.install_state not in {
        "installed",
        "ready",
    }:
        reasons.append("GAME_NOT_INSTALLED")

    if title.platform.lower() not in (
        node.operating_system or ""
    ).lower():
        reasons.append("UNSUPPORTED_OS")

    if maximum_vram_mb < title.minimum_vram_mb:
        reasons.append("INSUFFICIENT_VRAM")

    if memory_mb < title.minimum_memory_mb:
        reasons.append("INSUFFICIENT_RAM")

    if cpu_threads < title.minimum_cpu_threads:
        reasons.append("INSUFFICIENT_CPU")

    if storage_available_mb < title.minimum_storage_mb:
        reasons.append("INSUFFICIENT_STORAGE")

    if (
        title.streaming_backend == "sunshine"
        and not sunshine_ready
    ):
        reasons.append("SUNSHINE_UNAVAILABLE")

    row = db.scalar(
        select(NodeGameQualification).where(
            NodeGameQualification.node_id == node.id,
            NodeGameQualification.gaming_title_id == title.id,
        )
    )

    if row is None:
        row = NodeGameQualification(
            node_id=node.id,
            gaming_title_id=title.id,
        )
        db.add(row)

    row.qualified = not reasons
    row.reason_codes = reasons
    row.policy_version = title.qualification_policy_version
    row.evaluated_at = evaluated_at
    row.evidence = {
        "install_state": installation.install_state,
        "maximum_gpu_vram_mb": maximum_vram_mb,
        "gpu_vram_values_mb": _gpu_vram_values_mb(node),
        "memory_mb": memory_mb,
        "cpu_threads": cpu_threads,
        "storage_available_mb": storage_available_mb,
        "sunshine_ready": sunshine_ready,
    }


def reconcile_node_gaming_inventory(
    db: Session,
    node: Node,
) -> None:
    ensure_builtin_titles(db)

    games = (
        ((node.inventory or {}).get("gaming") or {}).get(
            "games"
        )
        or []
    )

    indexed: dict[tuple[str, str], dict] = {}

    for item in games:
        if not isinstance(item, dict):
            continue

        launcher = str(
            item.get("launcher") or ""
        ).lower()

        app_id = str(
            item.get("app_id")
            or item.get("launcher_app_id")
            or ""
        )

        if launcher and app_id:
            indexed[(launcher, app_id)] = item

    now = datetime.now(UTC)

    titles = list(
        db.scalars(
            select(GamingTitle).where(
                GamingTitle.enabled.is_(True)
            )
        )
    )

    for title in titles:
        observed = indexed.get(
            (
                title.launcher.lower(),
                title.launcher_app_id,
            )
        )

        row = db.scalar(
            select(NodeGameInventory).where(
                NodeGameInventory.node_id == node.id,
                NodeGameInventory.gaming_title_id
                == title.id,
            )
        )

        if row is None:
            row = NodeGameInventory(
                node_id=node.id,
                gaming_title_id=title.id,
            )
            db.add(row)

        row.launcher = title.launcher
        row.launcher_app_id = title.launcher_app_id
        row.observed_at = now

        if observed:
            row.install_state = str(
                observed.get("state")
                or (
                    "installed"
                    if observed.get("installed", True)
                    else "absent"
                )
            ).lower()

            row.install_path = str(
                observed.get("install_path") or ""
            )
            row.build_id = str(
                observed.get("build_id") or ""
            )
            row.manifest_path = str(
                observed.get("manifest_path") or ""
            )
            row.raw_metadata = dict(observed)
        else:
            row.install_state = "absent"
            row.install_path = ""
            row.build_id = ""
            row.manifest_path = ""
            row.raw_metadata = {}

        db.flush()

        qualify_node_game(
            db,
            node=node,
            title=title,
            installation=row,
            evaluated_at=now,
        )
