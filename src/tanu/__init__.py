"""
tanu - Voice assistant for DeskBot

A calm, sharp, slightly witty personal assistant.
"""

__version__ = "2.0.0"
__author__ = "Mithil Reddy"

LOGO = "🎙️"

from tanu.plugins.voice.deskbot import DeskbotConnection
from tanu.config import load_config, get_asset_path

__all__ = [
    "__version__",
    "LOGO",
    "DeskbotConnection",
    "load_config",
    "get_asset_path",
]
