from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "proto" / "nest.proto"
OUTPUT = ROOT / "silki_ai" / "generated"


def main() -> int:
    if not PROTO.exists():
        print("proto/nest.proto is missing. Download it from the CLOVA Speech console/docs.")
        return 1

    OUTPUT.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO.parent}",
        f"--python_out={OUTPUT}",
        f"--grpc_python_out={OUTPUT}",
        str(PROTO),
    ]
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
