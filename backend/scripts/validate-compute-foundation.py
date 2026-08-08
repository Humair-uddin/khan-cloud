#!/usr/bin/env python3
from __future__ import annotations

import json
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.node import Node
from app.services.compute_service import capacity_read, sync_node_capacity

NODE_NAME = "KC-R7425-VPS-01"


def main() -> None:
    with SessionLocal() as db:
        node = db.scalar(select(Node).where(Node.name == NODE_NAME))
        if node is None:
            raise RuntimeError("Real R7425 node is missing.")
        capacity = sync_node_capacity(db, node)
        view = capacity_read(node, capacity)
        if view.cpu_total != 128:
            raise RuntimeError(f"Unexpected R7425 logical CPU count: {view.cpu_total}")
        if view.cpu_allocatable >= view.cpu_total:
            raise RuntimeError("Host CPU reserve was not applied.")
        if view.memory_allocatable_bytes >= view.memory_total_bytes:
            raise RuntimeError("Host memory reserve was not applied.")
        if view.scheduling_enabled:
            raise RuntimeError(
                "R7425 unexpectedly became schedulable before explicit KVM/libvirt execution activation."
            )
        result = view.model_dump(mode="json")
        result["node_name"] = node.name
        result["status"] = "safe_foundation_verified"
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
