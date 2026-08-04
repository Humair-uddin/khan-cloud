from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from khan_agent.config import AgentSettings
from khan_agent.runtime import AgentRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Khan Cloud Universal Agent")
    parser.add_argument(
        "--config",
        default="/etc/khan-cloud-agent/config.yaml",
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run startup checks once and exit without starting the heartbeat loop.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = AgentSettings.load(Path(args.config))
    runtime = AgentRuntime(settings)
    asyncio.run(runtime.run(once=args.once))
