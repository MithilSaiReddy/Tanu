"""
tanu/plugins/voice/wakeword.py — Wake word detection for Tanu.

Entry point for always-listening mode. Uses openWakeWord by default,
with a pluggable interface so you can swap in any wake word engine.

Usage:
    listener = WakeWordListener(callback=my_fn, config=cfg)
    listener.start()
    # ... later ...
    listener.stop()

Config (in config.json under "wakeword"):
    {
        "enabled": true,
        "engine": "openwakeword",
        "model_path": "",
        "threshold": 0.5,
        "wake_word": "hey tanu"
    }
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

LOG = logging.getLogger(__name__)


# ── Abstract base ───────────────────────────────────────────────────

class WakeWordEngine(ABC):
    """Base class for wake word detection engines."""

    @abstractmethod
    def load(self, config: dict) -> None:
        """Load models / initialize the engine."""
        pass

    @abstractmethod
    def process_frame(self, audio_frame) -> float:
        """
        Process one audio frame. Return a detection score (0.0–1.0).
        Higher = more confident detection.
        """
        pass

    @abstractmethod
    def sample_rate(self) -> int:
        """Required sample rate in Hz (typically 16000)."""
        pass

    @abstractmethod
    def frame_size(self) -> int:
        """Required frame size in samples."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Release resources."""
        pass


# ── openWakeWord engine ─────────────────────────────────────────────

class OpenWakeWordEngine(WakeWordEngine):
    """Wake word detection using openWakeWord (ONNX-based)."""

    def __init__(self):
        self._model = None
        self._model_name = None

    def load(self, config: dict) -> None:
        try:
            from openwakeword.model import Model
        except ImportError:
            raise RuntimeError(
                "openWakeWord not installed.\n"
                "Run: pip install openwakeword\n"
                "Or set wakeword.engine to null to disable wake word."
            )

        model_path = config.get("model_path", "")
        models = [model_path] if model_path else []

        self._model = Model(wakeword_models=models)
        self._model_name = Path(model_path).stem if model_path else "default"
        LOG.info(f"[WakeWord] openWakeWord loaded: {model_path or 'built-in models'}")

    def process_frame(self, audio_frame) -> float:
        if self._model is None:
            return 0.0
        prediction = self._model.predict(audio_frame)
        return prediction.get(self._model_name, 0.0)

    def sample_rate(self) -> int:
        return 16000

    def frame_size(self) -> int:
        return 1280  # 80ms at 16kHz

    def unload(self) -> None:
        self._model = None


# ── Null engine (wake word disabled) ────────────────────────────────

class NullWakeWordEngine(WakeWordEngine):
    """No-op engine — wake word detection is disabled."""

    def load(self, config: dict) -> None:
        pass

    def process_frame(self, audio_frame) -> float:
        return 0.0

    def sample_rate(self) -> int:
        return 16000

    def frame_size(self) -> int:
        return 1280

    def unload(self) -> None:
        pass


# ── Listener ────────────────────────────────────────────────────────

class WakeWordListener:
    """
    Background thread that listens for a wake word.

    When detected, calls the provided callback function.
    Runs continuously until stopped.

    Example:
        def on_wake():
            print("Wake word detected!")

        listener = WakeWordListener(
            callback=on_wake,
            config={"enabled": True, "engine": "openwakeword", "model_path": "..."}
        )
        listener.start()
    """

    def __init__(
        self,
        callback: Callable[[], None],
        config: dict,
    ):
        self.callback = callback
        self._config = config.get("wakeword", config)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._engine: Optional[WakeWordEngine] = None

    def start(self) -> None:
        """Start the wake word listener in a background thread."""
        if self._running:
            return

        if not self._config.get("enabled", False):
            LOG.info("[WakeWord] Disabled in config")
            return

        engine_name = self._config.get("engine", "openwakeword")
        threshold = self._config.get("threshold", 0.5)

        if engine_name == "openwakeword":
            self._engine = OpenWakeWordEngine()
        else:
            LOG.warning(f"[WakeWord] Unknown engine '{engine_name}', using null")
            self._engine = NullWakeWordEngine()

        try:
            self._engine.load(self._config)
        except Exception as e:
            LOG.error(f"[WakeWord] Failed to load engine: {e}")
            return

        self._running = True
        self._threshold = threshold
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeWord")
        self._thread.start()
        LOG.info(f"[WakeWord] Started (engine={engine_name}, threshold={threshold})")

    def stop(self) -> None:
        """Stop the wake word listener."""
        self._running = False
        if self._engine:
            self._engine.unload()
        LOG.info("[WakeWord] Stopped")

    def _loop(self) -> None:
        """Main listening loop — reads audio frames and checks for wake word."""
        try:
            import sounddevice as sd
        except ImportError:
            LOG.error("[WakeWord] sounddevice not installed: pip install sounddevice")
            return

        sample_rate = self._engine.sample_rate()
        frame_size = self._engine.frame_size()

        try:
            with sd.InputStream(
                channels=1,
                samplerate=sample_rate,
                blocksize=frame_size,
                dtype="int16",
            ) as stream:
                LOG.info("[WakeWord] Listening...")
                while self._running:
                    try:
                        audio, overflowed = stream.read(frame_size)
                        if overflowed:
                            continue

                        score = self._engine.process_frame(audio[:, 0])

                        if score >= self._threshold:
                            LOG.info(f"[WakeWord] Detected! (score={score:.3f})")
                            self.callback()

                            # Cooldown: wait 2 seconds before listening again
                            time.sleep(2)

                    except Exception as e:
                        LOG.debug(f"[WakeWord] Frame error: {e}")
                        time.sleep(0.1)

        except Exception as e:
            LOG.error(f"[WakeWord] Audio stream error: {e}")

    @property
    def is_running(self) -> bool:
        return self._running


# ── Convenience ─────────────────────────────────────────────────────

def create_listener(config: dict, callback: Callable[[], None]) -> WakeWordListener:
    """Create a wake word listener from config."""
    return WakeWordListener(callback=callback, config=config)
