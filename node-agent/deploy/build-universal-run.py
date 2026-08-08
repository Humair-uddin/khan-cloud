from __future__ import annotations

import argparse
import base64
import io
import tarfile
from pathlib import Path


def build_run(bootstrap: Path, payload_dir: Path, output: Path) -> None:
    if not bootstrap.is_file():
        raise ValueError(f"Bootstrap missing: {bootstrap}")
    if not payload_dir.is_dir():
        raise ValueError(f"Payload directory missing: {payload_dir}")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for item in sorted(payload_dir.rglob("*")):
            if item.is_file():
                archive.add(item, arcname=item.relative_to(payload_dir))

    encoded = base64.encodebytes(buffer.getvalue())
    content = bootstrap.read_bytes()
    if not content.endswith(b"\n"):
        content += b"\n"
    output.write_bytes(content + encoded)
    output.chmod(0o700)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_run(args.bootstrap, args.payload, args.output)


if __name__ == "__main__":
    main()
