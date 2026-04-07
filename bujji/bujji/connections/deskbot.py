"""
bujji/connections/deskbot.py

Deskbot voice assistant using whisper.cpp (STT) + piper (TTS).
Three threads: STT → Agent → TTS

Features:
- subprocess-based STT (whisper.cpp) for low latency
- piper-tts Python library with persistent model (30x faster TTS)
- simulate mode for testing without microphone
"""

from __future__ import annotations

import io
import logging
import os
import queue
import re
import signal
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bujji.connections.display import BaseDisplay
    from bujji.session import SessionManager

LOG = logging.getLogger(__name__)

NOISE_PHRASES = {"huh", "uh", "um", "hmm", "okay", "ok", ""}

_tts_queue_ref: Optional[queue.Queue] = None
_simulate_queue_ref: Optional[queue.Queue] = None

_piper_voice: Optional["PiperVoice"] = None


def _get_piper_voice(model_path: str):
    """Get or create persistent piper voice (loads model once)."""
    global _piper_voice
    if _piper_voice is None:
        from piper import PiperVoice

        LOG.info(f"[TTS] Loading Piper model: {model_path}")
        _piper_voice = PiperVoice.load(model_path)
        LOG.info("[TTS] Piper model loaded")
    return _piper_voice


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

    return text.strip()[:500]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at [.!?] followed by whitespace, min 4 words."""
    if not text:
        return []

    sentences = []
    buffer = ""
    for char in text:
        buffer += char
        if re.search(r"[.!?]\s", buffer) and len(buffer.split()) >= 4:
            parts = re.split(r"(?<=[.!?])\s", buffer, maxsplit=1)
            if len(parts) == 2:
                sentences.append(parts[0].strip())
                buffer = parts[1]

    if buffer.strip():
        sentences.append(buffer.strip())

    return sentences


class DeskbotConnection:
    """Three-thread voice pipeline: STT → Agent → TTS using subprocesses."""

    def __init__(
        self,
        cfg: dict,
        mgr: "SessionManager",
        display: "BaseDisplay",
        simulate: bool = False,
        agent_name: str = "tanu",
        workspace: str = None,
    ):
        self.cfg = cfg
        self.mgr = mgr
        self.display = display
        self._simulate = simulate
        self._agent_name = agent_name
        self._workspace = workspace

        dc = cfg.get("deskbot", {})

        self._whisper_bin = os.path.expanduser(
            dc.get("whisper_bin", "~/whisper.cpp/main")
        )
        self._whisper_model = os.path.expanduser(
            dc.get("whisper_model", "~/whisper.cpp/models/ggml-tiny.en.bin")
        )
        self._whisper_threads = dc.get("whisper_threads", 4)

        self._piper_bin = os.path.expanduser(dc.get("piper_bin", "~/piper/piper"))
        self._piper_model = os.path.expanduser(
            dc.get("piper_model", "~/piper/voices/en_US-lessac-medium.onnx")
        )

        self._audio_input_device = dc.get("audio_input_device")

        self._input_queue: queue.Queue[str] = queue.Queue()
        self._tts_queue: queue.Queue[str] = queue.Queue()
        self._agent_cancel = threading.Event()

        global _tts_queue_ref, _simulate_queue_ref
        _tts_queue_ref = self._tts_queue
        if simulate:
            _simulate_queue_ref = self._input_queue

        self._running = False

    def run(self) -> None:
        """Start all three threads and block."""
        self._running = True

        LOG.info(f"[Deskbot] Starting (simulate={self._simulate})")
        LOG.info(f"[Deskbot] whisper={self._whisper_bin}")
        LOG.info(f"[Deskbot] piper={self._piper_bin}")

        if self._simulate:
            LOG.info("[Deskbot] Starting simulate thread...")
            t_sim = threading.Thread(
                target=self._simulate_thread, daemon=True, name="Simulate"
            )
            t_sim.start()
            LOG.info("[Deskbot] Simulate thread started")

        t_stt = threading.Thread(target=self._thread_stt, daemon=True, name="STT")
        t_agent = threading.Thread(target=self._thread_agent, daemon=True, name="Agent")
        t_tts = threading.Thread(target=self._thread_tts, daemon=True, name="TTS")

        t_stt.start()
        t_agent.start()
        t_tts.start()

        LOG.info("[Deskbot] Started (STT, Agent, TTS threads)")

        def signal_handler(sig, frame):
            LOG.info("[Deskbot] Shutting down...")
            self._running = False
            self.display.show_idle()

        old_handler = None
        if threading.current_thread() == threading.main_thread():
            old_handler = signal.signal(signal.SIGINT, signal_handler)

        try:
            while self._running:
                time.sleep(0.5)
        finally:
            if old_handler is not None:
                signal.signal(signal.SIGINT, old_handler)

    def _simulate_thread(self) -> None:
        """Simulate voice input - file injection OR direct typing."""
        LOG.info("[Simulate] Thread started")

        time.sleep(2)

        sim_file = "/tmp/deskbot_sim_input.txt"

        import sys

        is_tty = sys.stdin.isatty()

        LOG.info(f"[Simulate] Mode: TTY={is_tty}")

        if is_tty:
            print("\n=== Simulate Mode ===", flush=True)
            print("Type message + Enter to speak", flush=True)
            print("Type 'quit' to exit", flush=True)
            print("======================\n", flush=True)

            # Interactive mode - use input() in a separate thread
            def read_input():
                while self._running:
                    try:
                        text = input("You: ").strip()
                        if text.lower() in ("quit", "exit"):
                            LOG.info("[Simulate] Exit requested")
                            self._running = False
                            break
                        if text:
                            LOG.info(f"[Simulate] Input: '{text}'")
                            try:
                                self._input_queue.put(text, timeout=1)
                            except queue.Full:
                                LOG.warning("[Simulate] Queue full")
                    except (EOFError, KeyboardInterrupt):
                        break
                    except Exception as e:
                        LOG.debug(f"[Simulate] Input error: {e}")

            input_thread = threading.Thread(target=read_input, daemon=True)
            input_thread.start()
            input_thread.join()
        else:
            # Non-TTY mode - file-based or piped
            while self._running:
                text = None

                if os.path.exists(sim_file):
                    try:
                        with open(sim_file, "r") as f:
                            text = f.read().strip()
                        os.remove(sim_file)
                        if text:
                            LOG.info(f"[Simulate] File: '{text}'")
                    except Exception as e:
                        LOG.error(f"[Simulate] File error: {e}")

                if text:
                    try:
                        self._input_queue.put(text, timeout=1)
                    except queue.Full:
                        LOG.warning("[Simulate] Queue full")

                time.sleep(0.3)

        LOG.info("[Simulate] Thread exiting")

    def _thread_stt(self) -> None:
        """Thread 1: STT — use webrtcvad + whisper.cpp subprocess."""

        if self._simulate:
            LOG.info("[Deskbot] STT disabled (simulate mode)")
            return

        try:
            import webrtcvad
        except ImportError:
            LOG.error("[Deskbot] webrtcvad not installed: pip install webrtcvad")
            return

        try:
            import sounddevice as sd
        except ImportError:
            LOG.error("[Deskbot] sounddevice not installed: pip install sounddevice")
            return

        if not os.path.exists(self._whisper_bin):
            LOG.error(f"[Deskbot] whisper.cpp not found: {self._whisper_bin}")
            return

        if not os.path.exists(self._whisper_model):
            LOG.error(f"[Deskbot] whisper model not found: {self._whisper_model}")
            return

        vad = webrtcvad.Vad(2)
        sample_rate = 16000
        frame_duration = 30
        frames_per_buffer = int(sample_rate * frame_duration / 1000)

        audio_buffer = []
        silence_frames = 0
        max_silence = int(600 / frame_duration)

        LOG.info("[Deskbot] STT ready (webrtcvad + whisper.cpp)")

        def callback(indata, frames, time_info, status):
            nonlocal audio_buffer, silence_frames

            if status:
                LOG.debug(f"[STT] status: {status}")

            is_speech = vad.is_speech(indata[:, 0].tobytes(), sample_rate)

            if is_speech:
                audio_buffer.append(indata.copy())
                silence_frames = 0
            else:
                if audio_buffer:
                    silence_frames += 1
                    if silence_frames > max_silence:
                        self._process_audio_buffer(audio_buffer)
                        audio_buffer = []
                        silence_frames = 0

        try:
            with sd.InputStream(
                channels=1,
                samplerate=sample_rate,
                blocksize=frames_per_buffer,
                dtype="int16",
                device=self._audio_input_device,
                callback=callback,
            ):
                while self._running:
                    time.sleep(0.1)
        except Exception as e:
            LOG.error(f"[Deskbot] STT error: {e}")

    def _process_audio_buffer(self, buffer) -> None:
        """Write audio buffer to WAV and run whisper.cpp."""
        import numpy as np

        wav_path = "/tmp/deskbot_input.wav"

        audio_data = np.concatenate(buffer)

        with wave.open(wav_path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(audio_data.tobytes())

        LOG.info("[STT] Processing...")
        self.display.show_thinking()

        try:
            result = subprocess.run(
                [
                    self._whisper_bin,
                    "-t",
                    str(self._whisper_threads),
                    "-m",
                    self._whisper_model,
                    "-f",
                    wav_path,
                    "--no-timestamps",
                    "-otxt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            txt_path = wav_path + ".txt"
            if os.path.exists(txt_path):
                transcript = Path(txt_path).read_text().strip()
            else:
                transcript = result.stdout.strip()

            if transcript and len(transcript) >= 3:
                LOG.info(f"[STT] {transcript}")
                self._input_queue.put(transcript)
            else:
                LOG.debug("[STT] Empty transcript")

        except subprocess.TimeoutExpired:
            LOG.error("[STT] Timeout")
        except Exception as e:
            LOG.error(f"[STT] Error: {e}")

    def _thread_agent(self) -> None:
        """Thread 2: Agent — process input with streaming TTS."""
        LOG.info("[Deskbot] Agent thread ready")

        sentence_buffer = ""

        def on_token(token: str) -> None:
            """Called for each streamed token - detect sentences and queue to TTS."""
            nonlocal sentence_buffer
            sentence_buffer += token

            sentence = self._extract_sentence(sentence_buffer)
            if sentence:
                cleaned = _clean_for_tts(sentence)
                if cleaned:
                    LOG.info(f"[Agent] Sentence: {cleaned[:50]}...")
                    try:
                        self._tts_queue.put(cleaned, timeout=1)
                    except queue.Full:
                        LOG.warning("[Deskbot] TTS queue full")

                sentence_buffer = sentence_buffer[-50:]

        while self._running:
            try:
                text = self._input_queue.get(timeout=1)
            except queue.Empty:
                continue

            self._agent_cancel.set()
            self._agent_cancel = threading.Event()

            while not self._tts_queue.empty():
                try:
                    self._tts_queue.get_nowait()
                except queue.Empty:
                    break

            LOG.info(f"[Agent] {text[:50]}...")
            self.display.show_thinking()

            agent = self.mgr.get(
                "tanu",
                agent_name=self._agent_name,
                workspace=Path(self._workspace) if self._workspace else None,
            )

            sentence_buffer = ""
            history = self.mgr.history("tanu")

            try:
                result = agent.run(text, history=history, stream=True)
            except Exception as e:
                LOG.error(f"[Agent] Error: {e}")
                result = f"Sorry, I encountered an error."
                if sentence_buffer:
                    cleaned = _clean_for_tts(sentence_buffer)
                    if cleaned:
                        self._tts_queue.put(cleaned, timeout=1)

            if result:
                self.mgr.append("tanu", "user", text)
                self.mgr.append("tanu", "assistant", result)

                for sentence in _split_sentences(result):
                    cleaned = _clean_for_tts(sentence)
                    if cleaned:
                        LOG.debug(f"[TTS] {cleaned[:50]}...")
                        try:
                            self._tts_queue.put(cleaned, timeout=1)
                        except queue.Full:
                            LOG.warning("[Deskbot] TTS queue full")

            LOG.info(f"[Deskbot] Response queued")

    def _extract_sentence(self, text: str) -> str:
        """Extract complete sentence from buffer - ends with .!? and has 4+ words."""
        import re

        m = re.search(r"[.!?]\s*$", text)
        if not m:
            return ""

        sentence = text[: m.end()].strip()
        words = sentence.split()

        if len(words) >= 4:
            return sentence
        return ""

    def _thread_tts(self) -> None:
        """Thread 3: TTS — use piper subprocess with persistent process."""

        if not os.path.exists(self._piper_model):
            LOG.warning(f"[Deskbot] piper model not found: {self._piper_model}")
            return

        try:
            voice = _get_piper_voice(self._piper_model)
        except Exception as e:
            LOG.error(f"[Deskbot] Failed to load piper: {e}")
            return

        LOG.info("[Deskbot] TTS ready (piper-tts with persistent model)")

        while self._running:
            try:
                sentence = self._tts_queue.get(timeout=1)
            except queue.Empty:
                continue

            cleaned = _clean_for_tts(sentence)
            if not cleaned:
                continue

            self.display.show_speaking()

            try:
                audio_bytes = b""
                for chunk in voice.synthesize(cleaned):
                    if hasattr(chunk, "audio_int16_bytes"):
                        audio_bytes += chunk.audio_int16_bytes

                if audio_bytes:
                    with wave.open("/tmp/deskbot_tts.wav", "wb") as f:
                        f.setnchannels(1)
                        f.setsampwidth(2)
                        f.setframerate(22050)
                        f.writeframes(audio_bytes)

                    subprocess.run(
                        ["aplay", "-q", "/tmp/deskbot_tts.wav"],
                        capture_output=True,
                        timeout=10,
                    )

            except subprocess.TimeoutExpired:
                LOG.error("[TTS] Timeout")
            except Exception as e:
                LOG.error(f"[TTS] Error: {e}")

            try:
                if self._tts_queue.empty():
                    self.display.show_idle()
            except Exception:
                pass

    def speak_text(self, text: str) -> None:
        """Speak text via TTS queue (for speak_tool)."""
        for sentence in _split_sentences(text):
            cleaned = _clean_for_tts(sentence)
            if cleaned:
                try:
                    self._tts_queue.put(cleaned, timeout=5)
                except queue.Full:
                    LOG.warning("[speak_tool] TTS queue full")


def speak_text(text: str) -> None:
    """Speak text via singleton TTS (for speak_tool)."""
    global _tts_queue_ref
    if _tts_queue_ref is None:
        LOG.warning("[speak_tool] TTS not initialized")
        return

    for sentence in _split_sentences(text):
        cleaned = _clean_for_tts(sentence)
        if cleaned:
            try:
                _tts_queue_ref.put(cleaned, timeout=5)
            except queue.Full:
                LOG.warning("[speak_tool] TTS queue full")


def simulate_input(text: str) -> None:
    """Inject simulated input via file (for testing)."""
    with open("/tmp/deskbot_sim_input.txt", "w") as f:
        f.write(text)
    print(f"[Simulate] Wrote to file: {text}", flush=True)
    LOG.info(f"[Simulate] Wrote to file: {text}")
