from __future__ import annotations

import argparse
import sys

from app.db.database import SessionLocal
from app.services.gateway_orchestration_service import (
    GatewayOrchestrationError,
)
from app.services.gateway_reconciliation_worker import (
    reconcile_gateway_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile Khan Cloud public gateway desired state."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum mappings to process in this run.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    db = SessionLocal()

    try:
        try:
            result = reconcile_gateway_batch(
                db,
                limit=args.limit,
            )
        except (
            GatewayOrchestrationError,
            ValueError,
        ) as exc:
            print(
                f"gateway reconciliation failed: {exc}",
                file=sys.stderr,
            )
            return 1

        print(
            "gateway reconciliation complete:"
            f" selected={result.selected}"
            f" succeeded={result.succeeded}"
            f" failed={result.failed}"
        )

        if result.mapping_ids:
            print(
                "mapping_ids="
                + ",".join(
                    str(mapping_id)
                    for mapping_id in result.mapping_ids
                )
            )

        return 0 if result.failed == 0 else 2

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
