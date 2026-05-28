const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const SERVER_URL = "http://localhost:7337";
const SESSION_ID = "tanu-desktop";

let streaming = false;
let abortController = null;

const $ = (id) => document.getElementById(id);

const floatCircle  = $("float-circle");
const chatPanel    = $("chat-panel");
const chatHeader   = $("chat-header");
const messagesEl   = $("messages");
const msgInput     = $("msg-input");
const btnSend      = $("btn-send");
const btnClose     = $("btn-close");
const statusDot    = $("status-dot");
const statusText   = $("status-text");

// ── Drag (native window manager via left button) ──

let dragOccurred = false;

floatCircle.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  const startX = e.clientX;
  const startY = e.clientY;

  const onMove = (me) => {
    if (Math.abs(me.clientX - startX) > 3 || Math.abs(me.clientY - startY) > 3) {
      cleanup();
      dragOccurred = true;
      invoke("start_native_drag").finally(() => { dragOccurred = false; });
    }
  };

  const onUp = () => cleanup();
  const cleanup = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
  };

  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
});

// ── Drag chat panel via header ──

chatHeader.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  const startX = e.clientX;
  const startY = e.clientY;

  const onMove = (me) => {
    if (Math.abs(me.clientX - startX) > 3 || Math.abs(me.clientY - startY) > 3) {
      cleanup();
      invoke("start_native_drag");
    }
  };

  const onUp = () => cleanup();
  const cleanup = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
  };

  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
});

floatCircle.addEventListener("click", (e) => {
  if (dragOccurred) return;
  openChat();
});

// ── Mode switching ──

async function switchMode(mode) {
  if (mode === "chat") {
    document.body.className = "mode-chat";
    msgInput.focus();
    checkServer();
  } else {
    document.body.className = "mode-float";
    cancelStream();
  }
}

async function openChat() {
  await invoke("set_chat");
  switchMode("chat");
}

async function closeChat() {
  await invoke("set_floating");
  switchMode("floating");
}

// ── Listen for Rust mode-changed events (e.g. from hotkey) ──

listen("mode-changed", (event) => {
  switchMode(event.payload);
});

// ── Event listeners ──

btnClose.addEventListener("click", closeChat);

msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

btnSend.addEventListener("click", sendMessage);

// ── Server check ──

async function checkServer() {
  statusDot.className = "dot-offline";
  statusText.textContent = "Connecting...";
  try {
    const resp = await fetch(`${SERVER_URL}/api/status`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      statusDot.className = "dot-online";
      statusText.textContent = "Connected";
    } else {
      throw new Error("Not ok");
    }
  } catch {
    statusDot.className = "dot-error";
    statusText.textContent = "Server offline — run: python main.py serve";
  }
}

// ── Send message ──

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || streaming) return;

  msgInput.value = "";
  addMessage(text, "user");
  cancelStream();

  abortController = new AbortController();
  streaming = true;
  setInputEnabled(false);
  addTypingIndicator();

  try {
    const resp = await fetch(`${SERVER_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: SESSION_ID }),
      signal: abortController.signal,
    });

    if (!resp.ok) {
      removeTypingIndicator();
      addMessage(`Server error (${resp.status})`, "system");
      streaming = false;
      setInputEnabled(true);
      return;
    }

    removeTypingIndicator();
    const botMsgEl = addMessage("", "bot streaming");
    let fullContent = "";

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        try {
          const event = JSON.parse(jsonStr);
          if (event.type === "token") {
            fullContent += event.content;
            botMsgEl.textContent = fullContent;
            scrollToBottom();
          } else if (event.type === "done") {
            botMsgEl.classList.remove("streaming");
            botMsgEl.textContent = event.content || fullContent;
            fullContent = event.content || fullContent;
          } else if (event.type === "error") {
            botMsgEl.textContent = `Error: ${event.content}`;
            botMsgEl.classList.remove("streaming");
          } else if (event.type === "tool_start") {
            addMessage(`🔧 ${event.name}...`, "system");
          } else if (event.type === "tool_done") {
            const sysMsgs = messagesEl.querySelectorAll(".msg.system");
            if (sysMsgs.length > 0) {
              const last = sysMsgs[sysMsgs.length - 1];
              if (last.textContent.startsWith("🔧")) {
                last.remove();
              }
            }
          }
        } catch {
          // skip malformed JSON
        }
      }
    }

    // If content was streamed via tokens, the done event already removed streaming class
    if (fullContent && botMsgEl.classList.contains("streaming")) {
      botMsgEl.classList.remove("streaming");
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    removeTypingIndicator();
    addMessage(`Connection failed: ${err.message}`, "system");
  }

  streaming = false;
  setInputEnabled(true);
}

function cancelStream() {
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
}

// ── UI helpers ──

function addMessage(text, cls) {
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  if (text) el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function addTypingIndicator() {
  const el = document.createElement("div");
  el.className = "typing-indicator";
  el.id = "typing-indicator";
  el.innerHTML = "<span></span><span></span><span></span>";
  messagesEl.appendChild(el);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setInputEnabled(enabled) {
  msgInput.disabled = !enabled;
  btnSend.disabled = !enabled;
  if (enabled) msgInput.focus();
}

// ── Settings ──

const btnSettings   = $("btn-settings");
const settingsPanel = $("settings-panel");
const headerTitle   = $("header-title");

let gmailAuthUrl = null;

btnSettings.addEventListener("click", () => {
  const showing = settingsPanel.style.display !== "none";
  if (showing) {
    settingsPanel.style.display = "none";
    messagesEl.style.display = "";
    btnSettings.classList.remove("active");
    headerTitle.textContent = "Tanu";
  } else {
    settingsPanel.style.display = "flex";
    messagesEl.style.display = "none";
    btnSettings.classList.add("active");
    headerTitle.textContent = "Settings";
    checkGmailStatus();
  }
});

async function checkGmailStatus() {
  const statusEl = $("gmail-status");
  statusEl.textContent = "Checking...";
  try {
    const resp = await fetch(`${SERVER_URL}/api/gmail/status`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await resp.json();
    if (data.ok) {
      statusEl.textContent = "Connected";
      $("gmail-actions").style.display = "none";
      $("gmail-connected").style.display = "flex";
    } else {
      statusEl.textContent = "Not connected";
      $("gmail-actions").style.display = "";
      $("gmail-connected").style.display = "none";
    }
  } catch {
    statusEl.textContent = "Server offline";
  }
  $("gmail-auth-flow").style.display = "none";
}

$("btn-gmail-connect").addEventListener("click", async () => {
  const authFlow = $("gmail-auth-flow");
  authFlow.style.display = "flex";
  const msgEl = $("gmail-auth-msg");
  msgEl.textContent = "Getting auth URL...";
  msgEl.className = "auth-msg";

  try {
    const resp = await fetch(`${SERVER_URL}/api/gmail/auth-url`, {
      signal: AbortSignal.timeout(10000),
    });
    const data = await resp.json();
    if (!data.ok) {
      msgEl.textContent = data.error || "Failed to get auth URL";
      msgEl.className = "auth-msg error";
      return;
    }
    gmailAuthUrl = data.auth_url;
    msgEl.textContent = "Click the button below to open Google's authorization page.";
    msgEl.className = "auth-msg success";
  } catch (err) {
    msgEl.textContent = `Error: ${err.message}`;
    msgEl.className = "auth-msg error";
  }
});

$("btn-gmail-open-url").addEventListener("click", () => {
  if (gmailAuthUrl) {
    invoke("open_url_in_browser", { url: gmailAuthUrl });
    const msgEl = $("gmail-auth-msg");
    msgEl.textContent = "After authorizing, copy the full URL from the browser address bar and paste it below.";
    msgEl.className = "auth-msg";
  }
});

function extractCode(input) {
  try {
    const url = new URL(input);
    return url.searchParams.get("code") || input;
  } catch {
    return input;
  }
}

$("gmail-code-input").addEventListener("paste", () => {
  setTimeout(() => {
    const raw = $("gmail-code-input").value.trim();
    const extracted = extractCode(raw);
    if (extracted !== raw) $("gmail-code-input").value = extracted;
  }, 10);
});

$("btn-gmail-verify").addEventListener("click", async () => {
  const raw = $("gmail-code-input").value.trim();
  const code = extractCode(raw);
  if (!code) return;

  const msgEl = $("gmail-auth-msg");
  msgEl.textContent = "Verifying...";
  msgEl.className = "auth-msg";

  try {
    const resp = await fetch(`${SERVER_URL}/api/gmail/auth-complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await resp.json();
    if (data.ok) {
      msgEl.textContent = "Gmail connected successfully!";
      msgEl.className = "auth-msg success";
      $("gmail-code-input").value = "";
      $("gmail-auth-flow").style.display = "none";
      checkGmailStatus();
    } else {
      msgEl.textContent = data.error || "Verification failed";
      msgEl.className = "auth-msg error";
    }
  } catch (err) {
    msgEl.textContent = `Error: ${err.message}`;
    msgEl.className = "auth-msg error";
  }
});

$("btn-gmail-disconnect").addEventListener("click", async () => {
  try {
    await fetch(`${SERVER_URL}/api/gmail/disconnect`, {
      signal: AbortSignal.timeout(5000),
    });
  } catch {}
  checkGmailStatus();
});

// ── Init ──

async function init() {
  try {
    const mode = await invoke("get_mode");
    switchMode(mode);
  } catch {
    switchMode("floating");
  }
}

init();
