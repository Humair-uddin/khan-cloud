from __future__ import annotations

import os
import platform
from typing import Any


def collect_safe_inventory() -> dict[str, Any]:
    return {
        "cpu": {
            "model": platform.processor() or platform.machine(),
            "logical_count": os.cpu_count() or 0,
        },
        "memory": {
            "total_bytes": 0,
            "status": "not_collected_in_fp009",
        },
        "docker": {
            "available": False,
            "status": "not_collected_in_fp009",
        },
        "nvidia": {
            "available": False,
            "gpus": [],
            "status": "not_collected_in_fp009",
        },
    }
