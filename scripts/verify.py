#!/usr/bin/env python3
"""Repeatable, isolated verification for the checking branch."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def syntax_check() -> int:
    files = [ROOT / "main.py"]
    for folder in (ROOT / "src", ROOT / "tests"):
        files.extend(folder.rglob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"[ok] Python syntax: {len(files)} files")
    return len(files)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_json(url: str, deadline: float) -> dict | list:
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"endpoint did not become ready: {url}: {last_error}")


def process_tree_mb(pid: int) -> float:
    import psutil

    process = psutil.Process(pid)
    processes = [process, *process.children(recursive=True)]
    return sum(item.memory_info().rss for item in processes if item.is_running()) / 1024 / 1024


def full_server_check(env: dict[str, str]) -> None:
    for dependency in ("aiohttp", "requests", "psutil"):
        subprocess.run(
            [sys.executable, "-c", f"import {dependency}"],
            cwd=ROOT,
            env=env,
            check=True,
        )

    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "main.py", "serve", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        status = read_json(f"{base}/api/status", deadline)
        config = read_json(f"{base}/api/config", deadline)
        tools = read_json(f"{base}/api/tools", deadline)
        events = read_json(f"{base}/api/events", deadline)
        if not isinstance(status, dict) or not isinstance(config, dict):
            raise RuntimeError("status/config endpoints returned invalid data")
        if not isinstance(tools, (dict, list)) or not isinstance(events, (dict, list)):
            raise RuntimeError("tools/events endpoints returned invalid data")
        used_mb = process_tree_mb(process.pid)
        hard_limit = float(status.get("memory", {}).get("hard_limit_mb", 800))
        if used_mb >= hard_limit:
            raise RuntimeError(f"server used {used_mb:.1f} MB (limit {hard_limit:.0f} MB)")
        print(f"[ok] Local API endpoints; process tree {used_mb:.1f} MB / {hard_limit:.0f} MB")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.returncode not in (0, -15, 1):
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"server exited with {process.returncode}:\n{output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="also test installed dependencies and local API")
    args = parser.parse_args()

    syntax_check()
    with tempfile.TemporaryDirectory(prefix="tanu-verify-") as temporary:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(ROOT / "src")
        env["TANU_CONFIG_DIR"] = str(Path(temporary) / "config")
        env["TANU_WORKSPACE_DIR"] = str(Path(temporary) / "workspace")

        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], env)
        run([sys.executable, "main.py", "--help"], env)
        run([sys.executable, "main.py", "status"], env)
        if args.full:
            full_server_check(env)

    print("[ok] Verification complete; temporary test data removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
