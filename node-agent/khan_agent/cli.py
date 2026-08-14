from __future__ import annotations

import argparse
import platform
import asyncio
from pathlib import Path

from khan_agent.config import AgentSettings, _default_state_directory
from khan_agent.runtime import AgentRuntime



def _default_config_path() -> Path:
    state_directory = _default_state_directory()

    if platform.system() == "Windows":
        return state_directory / "config.yaml"

    return Path("/etc/khan-cloud-agent/config.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Khan Cloud Universal Agent")
    parser.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Path to YAML configuration file.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--once", action="store_true")
    action.add_argument("--enroll", action="store_true")
    action.add_argument("--heartbeat-once", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = AgentSettings.load(Path(args.config))
    runtime = AgentRuntime(settings)

    if args.enroll:
        asyncio.run(runtime.enroll_once())
    elif args.heartbeat_once:
        asyncio.run(runtime.heartbeat_once())
    else:
        asyncio.run(runtime.run(once=args.once))
