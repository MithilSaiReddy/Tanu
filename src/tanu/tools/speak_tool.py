"""
bujji/tools/speak_tool.py

Proactive TTS tool for deskbot. Lets the agent speak spontaneously.
Uses the main deskbot TTS engine if available, otherwise prints to stdout.
"""

from __future__ import annotations

import logging
import queue
import re
from typing import Optional

from bujji.tools.base import ToolContext, param, register_tool

LOG = logging.getLogger(__name__)

_tts_queue: Optional[queue.Queue[str]] = None
_print_mode = False


def set_tts_queue(q: queue.Queue[str]) -> None:
    """Set the TTS queue (called by deskbot.py on init)."""
    global _tts_queue
    _tts_queue = q


def set_print_mode(enabled: bool) -> None:
    """Enable text output mode (for testing without audio)."""
    global _print_mode
    _print_mode = enabled


def _split_sentences(text: str):
    """Split text into sentences at [.!?] + whitespace."""
    if not text:
        return

    buffer = ""
    for char in text:
        buffer += char
        if re.search(r"[.!?]\s", buffer) and len(buffer.split()) >= 4:
            parts = re.split(r"(?<=[.!?])\s", buffer, maxsplit=1)
            if len(parts) == 2:
                yield parts[0].strip()
                buffer = parts[1]

    if buffer.strip():
        yield buffer.strip()


def _clean_for_tts(text: str) -> str:
    """Clean text for TTS output."""
    if not text:
        return ""

    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"https?://[^\s]+", "link", text)

    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"
        "\U0001f300-\U0001f5ff"
        "\U0001f680-\U0001f6ff"
        "\U0001f1e0-\U0001f1ff"
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


@register_tool(
    description=(
        "Speak the given text aloud via TTS. Use this when the response would "
        "benefit from being heard rather than just displayed, such as notifications, "
        "status updates, or time-sensitive information."
    ),
    params=[
        param("text", "The text to speak. Keep it concise and natural."),
    ],
)
def speak(text: str, _ctx: ToolContext = None) -> str:
    """Speak text via TTS or print to stdout."""
    if not text:
        return "(empty text)"

    if _print_mode:
        for sentence in _split_sentences(text):
            cleaned = _clean_for_tts(sentence)
            if cleaned:
                print(cleaned)
        return f"Printed: {len(text)} chars"

    if _tts_queue is None:
        for sentence in _split_sentences(text):
            cleaned = _clean_for_tts(sentence)
            if cleaned:
                print(f"[speak] {cleaned}")
        return f"Printed: {len(text)} chars (no TTS)"

    spoken = 0
    for sentence in _split_sentences(text):
        cleaned = _clean_for_tts(sentence)
        if cleaned:
            try:
                _tts_queue.put(cleaned, timeout=5)
                spoken += len(cleaned)
            except queue.Full:
                return f"TTS queue full, spoke {spoken} chars"

    return f"Speaking: {spoken} chars"


@register_tool(
    description=(
        "Show text on the deskbot display. Use for anything better seen than heard: "
        "lists, addresses, code, schedules, numbers, directions."
    ),
    params=[
        param("text", "The text to display."),
    ],
)
def show_on_display(text: str, _ctx: ToolContext = None) -> str:
    """Display text on screen."""
    if not text:
        return "(empty text)"
    return f"Display: {text[:100]}"
