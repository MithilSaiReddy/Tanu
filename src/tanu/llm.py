"""
tanu/llm.py  —  v3

LLMProvider — OpenAI-compatible /v1/chat/completions with:
• token_cb   : callback for streamed tokens instead of print-to-stdout
              → decouples the LLM from the output channel (CLI / web UI / tests)
• Retry with honour of the provider's Retry-After header and jittered
  exponential backoff; 429 rate-limits are given the most patience because
  they are window-based (per-minute) rather than per-request
• Retry budget is configurable via max_retries
• Reused requests.Session — skips the TCP/TLS handshake on every call
• Anthropic auth handled transparently
"""
from __future__ import annotations

import json
import random
import sys
import time
from threading import Event as _Event
from typing import Callable, Optional

_RETRY_STATUS = {429, 500, 502, 503, 504}
_BACKOFF_BASE = 2.0
_MAX_WAIT     = 60.0          # ceiling for any single backoff/Retry-After sleep
_JITTER       = 0.20          # ±20% random spread to avoid synchronized retries

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class LLMError(Exception):
    """Raised when the provider returns a non-retryable error.

    `.status` holds the HTTP status code (or 0 for connection failures),
    `.message` the provider-facing detail.
    """

    def __init__(self, status: int, message: str):
        super().__init__(f"API error {status}: {message}")
        self.status  = status
        self.message = message

class LLMProvider:
    """
    Thin wrapper around any OpenAI-compatible /v1/chat/completions endpoint.

    Parameters
    ──────────
    token_cb : optional callable(str) — receives each streamed token.
               If None, tokens are printed to stdout (original CLI behaviour).
    """

    def __init__(
        self,
        name:        str,
        api_key:     str,
        api_base:    str,
        model:       str,
        max_tokens:  int   = 8192,
        temperature: float = 0.7,
        max_retries: int   = 5,
        connect_timeout: int = 8,
        read_timeout: int = 60,
    ):
        self.name        = name
        self.api_key     = api_key
        self.api_base    = api_base.rstrip("/")
        self.model       = model
        self.max_tokens  = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = (
            max(1, min(int(connect_timeout), 30)),
            max(5, min(int(read_timeout), 180)),
        )
        # Reused connection pool — skips the TCP/TLS handshake on every call,
        # which is the biggest per-turn latency win for multi-turn sessions.
        self._session = _requests.Session() if _HAS_REQUESTS else None

    # ── Public ────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list,
        tools:    Optional[list]                      = None,
        stream:   bool                                = False,
        token_cb: Optional[Callable[[str], None]]     = None,
        cancel_event: Optional[_Event]                = None,
    ) -> dict:
        """
        Send a chat request.

        If stream=True:
          • Calls token_cb(token) for each token (if provided)
          • Falls back to print(token) if token_cb is None
        If cancel_event is set while streaming, the request is abandoned and
        a partial synthetic dict is returned.
        Returns a synthetic dict shaped like a non-streamed OpenAI response.
        """
        if not _HAS_REQUESTS:
            raise RuntimeError("requests not installed — run: pip install requests")

        url     = f"{self.api_base}/chat/completions"
        headers = self._build_headers()
        payload = self._build_payload(messages, tools, stream)
        resp    = self._post_with_retry(url, headers, payload, stream)

        if stream:
            return self._collect_stream(resp, token_cb=token_cb, cancel_event=cancel_event)
        return resp.json()

    # ── Private ───────────────────────────────────────────────────────────

    def _build_headers(self) -> dict:
        h = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.name == "anthropic":
            h["x-api-key"]         = self.api_key
            h["anthropic-version"] = "2023-06-01"
        return h

    def _build_payload(self, messages, tools, stream) -> dict:
        p: dict = {
            "model":       self.model,
            "messages":    messages,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "stream":      stream,
        }
        if tools:
            p["tools"]       = tools
            p["tool_choice"] = "auto"
        return p

    def _post_with_retry(self, url, headers, payload, stream):
        last_exc = None
        status   = 0
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    url, headers=headers, json=payload,
                    timeout=self.timeout, stream=stream,
                )
            except _requests.exceptions.ConnectionError as e:
                last_exc = LLMError(
                    0,
                    "Cannot connect to {url}.\n"
                    "Check your API base URL and network connection.".format(url=url),
                )
                if attempt < self.max_retries:
                    wait = self._backoff(attempt, status)
                    print(
                        f"[WARN] Connection error (attempt {attempt+1}/{self.max_retries}), "
                        f"retrying in {wait:.1f}s…",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                continue

            status = resp.status_code
            if status not in _RETRY_STATUS:
                if not resp.ok:
                    try:
                        body = resp.json()
                        msg  = body.get("error", {}).get("message", resp.text[:400])
                    except Exception:
                        msg  = resp.text[:400]
                    raise LLMError(status, msg)
                return resp

            last_exc = LLMError(status, resp.text[:200])
            if attempt < self.max_retries:
                wait = self._retry_wait(status, resp.headers, attempt)
                print(
                    f"[WARN] HTTP {status} (attempt {attempt+1}/{self.max_retries}), "
                    f"retrying in {wait:.1f}s…",
                    file=sys.stderr,
                )
                time.sleep(wait)

        raise last_exc or LLMError(0, "All retry attempts failed.")

    @staticmethod
    def _retry_wait(status: int, headers, attempt: int) -> float:
        """Wait time for a retryable HTTP status.

        429 (rate limit) and 503 get the most patience — they are window-based
        (per-minute limits), so a burst of fast retries all fail inside the same
        window. If the provider sends a Retry-After header it is honoured
        (capped at _MAX_WAIT); otherwise use jittered exponential backoff.
        """
        retry_after = headers.get("Retry-After") if headers is not None else None
        if retry_after:
            try:
                return min(float(retry_after), _MAX_WAIT)
            except (TypeError, ValueError):
                pass
        return LLMProvider._backoff(attempt, status)

    @staticmethod
    def _backoff(attempt: int, status: int) -> float:
        base  = _BACKOFF_BASE
        cap   = _MAX_WAIT if status == 429 else min(_MAX_WAIT, 15.0)
        wait  = base ** (attempt + 1)
        wait  = min(wait, cap) * (1.0 + random.uniform(-_JITTER, _JITTER))
        return max(wait, 0.5)

    def _collect_stream(
        self,
        response,
        token_cb: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[_Event] = None,
    ) -> dict:
        """Consume SSE stream, emit tokens via callback (or stdout), return synthetic dict."""
        full_content:   str            = ""
        tool_calls_raw: dict[int, dict] = {}
        finish_reason:  Optional[str]   = None
        cancelled:      bool            = False

        for raw_line in response.iter_lines():
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data: "):
                line = line[6:]
            if line == "[DONE]":
                break

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})

                token = delta.get("content")
                if token:
                    full_content += token
                    if token_cb:
                        token_cb(token)
                    else:
                        print(token, end="", flush=True)

                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.get("id"):
                        tool_calls_raw[idx]["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        tool_calls_raw[idx]["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        tool_calls_raw[idx]["function"]["arguments"] += fn["arguments"]

                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

        if full_content and not token_cb:
            print()  # newline after stdout streaming
        if cancelled:
            response.close()

        msg: dict = {"role": "assistant", "content": full_content or None}
        if tool_calls_raw:
            msg["tool_calls"] = [tool_calls_raw[i] for i in sorted(tool_calls_raw)]

        return {
            "choices": [{"message": msg, "finish_reason": finish_reason or "stop"}],
            "cancelled": cancelled,
        }
