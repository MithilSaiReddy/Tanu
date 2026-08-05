"""
tanu — ultra-lightweight personal AI assistant for DeskBot.

A calm, sharp, slightly witty personal assistant.
"""

__version__ = "2.0.0"
__author__ = "Mithil Reddy"

LOGO = "🎙️"

from tanu.config import (
    get_active_provider,
    get_asset_path,
    get_deskbot_config,
    load_config,
    save_config,
    workspace_path,
)
from tanu.agent import AgentLoop, CronService, HeartbeatService
from tanu.session import SessionManager

__all__ = [
    "__version__",
    "LOGO",
    "load_config",
    "save_config",
    "get_active_provider",
    "workspace_path",
    "get_asset_path",
    "get_deskbot_config",
    "AgentLoop",
    "HeartbeatService",
    "CronService",
    "SessionManager",
]
