#!/usr/bin/env python3
"""
Tanu - Voice assistant for DeskBot

Usage:
    python main.py tanu              # Start voice assistant
    python main.py tanu --text       # Text mode (no audio)
    python main.py onboard           # First-time setup
    python main.py serve             # Web UI (HTTP + WebSocket)
    python main.py desk              # Desktop app (Pygame UI + server)
    python main.py agent             # Chat in terminal

Requirements:
    pip install -e .            # Install Tanu package
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_src_path = os.path.join(_script_dir, "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import argparse
import multiprocessing
import signal
import threading
import time

from tanu import LOGO as TANU_LOGO
from tanu.config import load_config, workspace_path, get_active_provider
from tanu.identity import ensure_identity_files
from tanu.session import SessionManager
from tanu.agent import HeartbeatService, CronService


def cmd_onboard(args):
    from tanu.onboard import run_onboard
    run_onboard()


def cmd_tanu(args):
    from tanu.config import load_config
    from tanu.plugins.voice.deskbot import DeskbotConnection

    cfg = load_config()
    mgr = SessionManager(cfg)
    ws = Path(cfg["agents"]["defaults"]["workspace"])

    simulate = getattr(args, "simulate", False)
    text_mode = getattr(args, "text_mode", False)

    if text_mode:
        cmd_tanu_text(cfg, mgr)
        return

    display = None
    try:
        from tanu.plugins.voice.display import init_display
        display = init_display(cfg)
    except Exception:
        pass

    conn = DeskbotConnection(cfg, mgr, display, simulate=simulate)

    try:
        from tools.tanu_reminder import init_worker
        reminder_worker = init_worker(ws)
        reminder_worker.start()
    except Exception:
        reminder_worker = None

    heartbeat = HeartbeatService(mgr.get("tanu"), ws)
    cron = CronService(mgr.get("tanu"), ws)

    print(f"\n🎙️ Tanu voice assistant running")
    print("Press Ctrl+C to stop.\n")

    threads = [
        threading.Thread(target=conn.run, daemon=True),
        threading.Thread(target=heartbeat.start, daemon=True),
        threading.Thread(target=cron.start, daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🎙️ Shutting down...")
        if reminder_worker:
            reminder_worker.stop()


def cmd_tanu_text(cfg, mgr):
    from tanu.tools.speak_tool import set_print_mode
    ws = Path(cfg["agents"]["defaults"]["workspace"])

    set_print_mode(True)

    print(f"\n🎙️ Tanu text mode (Ctrl+D to exit)\n")

    import sys
    while True:
        try:
            line = input("You: ").strip()
            if not line:
                continue

            agent = mgr.get("tanu")
            result = agent.run(line, stream=False)
            if result:
                print(f"Tanu: {result}")
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            break


def cmd_serve(args):
    from tanu.config import load_config
    from tanu.server import run_server
    cfg = load_config()
    port = getattr(args, "port", 7337) or 7337
    run_server(cfg, port=port, quiet=True)


def cmd_status(args):
    from tanu import __version__
    from tanu.config import load_config

    cfg = load_config()
    pname, api_key, api_base, model = get_active_provider(cfg)
    ws = workspace_path(cfg)

    print(f"\n🎙️ Tanu v{__version__}")
    print(f"  Config: {cfg}")
    print(f"  Provider: {pname} / {model}")
    print(f"  Workspace: {ws}")
    print(f"  Web UI: python main.py serve → http://localhost:7337\n")


def _run_server(port: int):
    """Run the tanu server in a subprocess (quiet, API-only, no browser)."""
    from tanu.config import load_config
    from tanu.server import run_server
    cfg = load_config()
    run_server(cfg, port=port, quiet=True)


def cmd_update(args):
    from tanu.updater import run_update

    rc = run_update(
        check=getattr(args, "check", False),
        stash=getattr(args, "stash", False),
        force=getattr(args, "force", False),
        yes=getattr(args, "yes", False),
        deps=not getattr(args, "no_deps", False),
        build=not getattr(args, "no_build", False),
    )
    raise SystemExit(rc)


def cmd_desk(args):
    port = getattr(args, "port", 7337) or 7337

    from tanu.config import load_config
    from tanu.desktop.panel import (
        get_panel_cfg,
        resolve_display_mode,
    )
    cfg = load_config()
    mode = resolve_display_mode(getattr(args, "panel", False), cfg)
    panel_cfg = get_panel_cfg(cfg) if mode == "panel" else {}
    driver = "fbdev" if mode == "panel" else "window"

    print("Starting server + desktop app...")
    print(f"   Server:  http://localhost:{port}")
    print(f"   WS:      ws://localhost:{port}/ws/chat")
    print(f"   UI:      {driver} ({mode} mode)")

    try:
        from tanu.notifier import notify
        notify("Tanu", "Running in background.", timeout=4)
    except Exception:
        pass

    server_proc = multiprocessing.Process(target=_run_server, args=(port,), daemon=True)
    server_proc.start()

    if mode == "panel":
        _run_fbdev_panel(port, cfg, panel_cfg, server_proc)
    else:
        _run_pygame_desk(port, mode, cfg, server_proc)


def _run_fbdev_panel(port, cfg, panel_cfg, server_proc):
    """Run the pure-Python fbdev panel (Pillow -> /dev/fb0) in-process."""
    from tanu.desktop.fbdev_panel import run_panel
    from tanu.desktop.panel import _validate_framebuffer

    _validate_framebuffer(panel_cfg.get("device", "/dev/fb0"))
    ws_url = f"ws://127.0.0.1:{port}/ws/chat"

    def _shutdown(sig=None, frame=None):
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        run_panel(panel_cfg, ws_url)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down...")
        server_proc.terminate()
        try:
            server_proc.join(timeout=5)
        except Exception:
            pass
        if server_proc.is_alive():
            server_proc.kill()


def _run_pygame_desk(port, mode, cfg, server_proc):
    """Launch the Pygame desktop UI (original path)."""
    def _request_quit(sig=None, frame=None):
        try:
            import pygame
            if pygame.get_init():
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
        except Exception:
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _request_quit)
    signal.signal(signal.SIGTERM, _request_quit)

    exit_code = 0
    try:
        from tanu.desktop.app import TanuDesktopApp
        TanuDesktopApp(
            host="127.0.0.1", port=port, display_mode=mode, cfg=cfg
        ).run()
    except KeyboardInterrupt:
        print()
    except (FileNotFoundError, PermissionError) as e:
        print(f"\n{e}")
        exit_code = 1
    except ModuleNotFoundError as e:
        if "pygame" in str(e) or "websocket" in str(e):
            print(f"Missing dependency: {e}")
            print("   Run: pip install -r requirements.txt")
            exit_code = 1
        else:
            raise
    finally:
        print("\nShutting down...")
        server_proc.terminate()
        try:
            server_proc.join(timeout=5)
        except Exception:
            pass
        if server_proc.is_alive():
            server_proc.kill()

    if exit_code:
        raise SystemExit(exit_code)


def _ensure_workspace():
    """Scaffold missing identity files (USER.md, SOUL.md, etc.) on first run."""
    cfg = load_config()
    ws = workspace_path(cfg)
    ensure_identity_files(ws)
    user_md = ws / "USER.md"
    user_bak = ws / "USER.md.bak"
    if user_md.exists() and not user_bak.exists():
        user_bak.write_bytes(user_md.read_bytes())


def main():
    _ensure_workspace()
    parser = argparse.ArgumentParser(prog="tanu", description="🎙️ Voice assistant for DeskBot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup")
    sub.add_parser("serve", help="Web UI")
    sub.add_parser("status", help="Show status")
    p_desk = sub.add_parser("desk", help="Desktop app (Pygame + server)")
    p_desk.add_argument("--port", type=int, default=7337, help="Server port")
    p_desk.add_argument("--panel", action="store_true",
                        help="Render to TFT framebuffer (/dev/fb0) for SBCs")

    p_update = sub.add_parser("update", help="Update Tanu from GitHub")
    p_update.add_argument("--check", action="store_true", help="Check for updates without pulling")
    p_update.add_argument("--stash", action="store_true", help="Auto-stash local changes before pulling")
    p_update.add_argument("--force", action="store_true", help="Skip the dirty-tree check")
    p_update.add_argument("-y", "--yes", dest="yes", action="store_true", help="Skip the confirmation prompt")
    p_update.add_argument("--no-deps", dest="no_deps", action="store_true", help="Skip pip reinstall")
    p_update.add_argument("--no-build", dest="no_build", action="store_true", help="Deprecated (no-op)")

    p_tanu = sub.add_parser("tanu", help="Start voice assistant")
    p_tanu.add_argument("--text", dest="text_mode", action="store_true", help="Text mode")
    p_tanu.add_argument("--simulate", action="store_true", help="Simulate voice")

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "tanu": cmd_tanu,
        "serve": cmd_serve,
        "status": cmd_status,
        "desk": cmd_desk,
        "update": cmd_update,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()