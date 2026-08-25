"""
Entry point: python -m tanu.desktop [--host H] [--port N]
"""

import argparse

from .app import run_app


def main():
    parser = argparse.ArgumentParser(prog="tanu.desktop", description="Tanu desktop UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7337)
    args = parser.parse_args()
    run_app(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
