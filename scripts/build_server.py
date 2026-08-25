#!/usr/bin/env python3
"""
Frozen-server entry point (PyInstaller).

Usage:
    tanu-server                 # serve on 127.0.0.1:7337
    tanu-server --port 9000     # custom port
    tanu-server onboard         # interactive first-time LLM setup (terminal)
"""
import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="tanu-server", description="Tanu backend server")
    parser.add_argument("--port", type=int, default=7337, help="HTTP/WebSocket port (default 7337)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("command", nargs="?", choices=["onboard"], help="Optional: run onboarding wizard")
    args = parser.parse_args()

    from tanu.config import load_config

    if args.command == "onboard":
        from tanu.onboard import run_onboard
        run_onboard()
        return 0

    cfg = load_config()
    from tanu.server import run_server
    run_server(cfg, host=args.host, port=args.port, quiet=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
