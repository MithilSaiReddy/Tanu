"""
Entry point: python -m tanu.desktop [--host H] [--port N] [--panel]
"""

import argparse

from .app import run_app


def main():
    parser = argparse.ArgumentParser(prog="tanu.desktop", description="Tanu desktop UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7337)
    parser.add_argument(
        "--panel", action="store_true",
        help="Render to the TFT framebuffer (/dev/fb0) instead of a window",
    )
    args = parser.parse_args()

    from tanu.config import load_config
    from .panel import resolve_display_mode

    cfg = load_config()
    mode = resolve_display_mode(args.panel, cfg)

    try:
        run_app(host=args.host, port=args.port, display_mode=mode, cfg=cfg)
    except (FileNotFoundError, PermissionError) as e:
        print(f"[desktop] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
