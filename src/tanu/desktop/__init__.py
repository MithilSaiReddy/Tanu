"""
tanu.desktop — Pygame desktop UI for Tanu.

Replaces the Godot 4 client. Connects to the Tanu server over WebSocket
and renders the animated character face + chat interface.
"""

from .app import TanuDesktopApp, run_app

__all__ = ["TanuDesktopApp", "run_app"]
