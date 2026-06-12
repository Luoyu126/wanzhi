#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Wanzhi LLM GGUF RSS and Locked memory.")
    parser.add_argument("--service", default="wanzhi-llm.service")
    parser.add_argument("--model-name", default="qwen2.5-3b-instruct-q4_k_m.gguf")
    args = parser.parse_args()

    pid = _service_pid(args.service)
    if pid <= 0:
        raise SystemExit(f"{args.service} is not running")

    status = Path(f"/proc/{pid}/status").read_text(errors="replace")
    for line in status.splitlines():
        if line.startswith(("VmSize:", "VmRSS:", "VmHWM:", "VmLck:", "RssAnon:", "RssFile:")):
            print(line)

    size = rss = pss = locked = 0
    current = False
    for line in Path(f"/proc/{pid}/smaps").read_text(errors="replace").splitlines():
        if "-" in line and line[:1].isalnum():
            current = args.model_name in line
            continue
        if not current:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            value = int(parts[1])
        except ValueError:
            continue
        if key == "Size":
            size += value
        elif key == "Rss":
            rss += value
        elif key == "Pss":
            pss += value
        elif key == "Locked":
            locked += value

    print(f"model Size kB: {size}")
    print(f"model Rss kB: {rss}")
    print(f"model Pss kB: {pss}")
    print(f"model Locked kB: {locked}")
    if size and locked >= size * 0.95:
        print("PASS: model mapping is effectively locked")
    else:
        print("FAIL: model mapping is not fully locked")
        raise SystemExit(1)


def _service_pid(service: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", service, "-p", "MainPID", "--value"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return int(result.stdout.strip() or "0")


if __name__ == "__main__":
    main()
