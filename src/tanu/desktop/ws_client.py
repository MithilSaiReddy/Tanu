"""
WebSocket client for the desktop UI.

Ports src/godot/autoload/ws.gd: maintains a connection to the Tanu server,
streams incoming JSON events into a queue for the UI thread, buffers
outgoing sends while disconnected, and reconnects automatically.
"""

import json
import queue
import threading

import websocket


class WSClient:
    def __init__(
        self,
        url: str = "ws://127.0.0.1:7337/ws/chat",
        session_id: str = "desktop:main",
        reconnect_interval: float = 3.0,
    ):
        self.url = url
        self.session_id = session_id
        self.reconnect_interval = reconnect_interval

        self.events: queue.Queue[dict] = queue.Queue()
        self.connected = threading.Event()

        self._ws = None
        self._lock = threading.Lock()
        self._pending = []
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def is_connected(self) -> bool:
        return self.connected.is_set()

    def send(self, data: dict):
        with self._lock:
            if not self.connected.is_set() or self._ws is None:
                self._pending.append(data)
                return
        try:
            self._ws.send(json.dumps(data))
        except Exception:
            with self._lock:
                self._pending.append(data)
                self.connected.clear()

    def send_chat(self, message: str):
        self.send({"type": "chat", "message": message, "session_id": self.session_id})

    def request_status(self):
        self.send({"type": "status"})

    def _run_forever(self):
        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass
            finally:
                self.connected.clear()
            if self._stop.wait(self.reconnect_interval):
                break
        self.connected.clear()

    def _on_open(self, ws):
        self.connected.set()
        self.events.put({"type": "_connected"})
        self._flush_pending()

    def _on_message(self, ws, text):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            self.events.put({"type": "error", "message": "Invalid JSON from server"})
            return
        if isinstance(data, dict):
            self.events.put(data)

    def _on_close(self, ws, code, reason):
        self.connected.clear()
        self.events.put({"type": "_disconnected"})

    def _on_error(self, ws, error):
        pass

    def _flush_pending(self):
        with self._lock:
            pending, self._pending = self._pending, []
        ws = self._ws
        for msg in pending:
            try:
                ws.send(json.dumps(msg))
            except Exception:
                with self._lock:
                    self._pending = [msg] + self._pending
                return
