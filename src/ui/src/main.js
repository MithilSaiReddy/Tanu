const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const SERVER_URL = "http://localhost:7337";
const SESSION_ID = "tanu-desktop";

let streaming = false;
let abortController = null;
let historyOffset = 0;
const HISTORY_PAGE = 50;
let historyLoaded = false;

const PROVIDERS = {
  openrouter: { api_base: "https://openrouter.ai/api/v1",                    model: "openai/gpt-4o-mini" },
  openai:     { api_base: "https://api.openai.com/v1",                       model: "gpt-4o-mini" },
  anthropic:  { api_base: "https://api.anthropic.com/v1",                    model: "claude-3-haiku-20240307" },
  groq:       { api_base: "https://api.groq.com/openai/v1",                  model: "llama3-8b-8192" },
  google:     { api_base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.0-flash" },
  mistral:    { api_base: "https://api.mistral.ai/v1",                       model: "mistral-small-latest" },
  zhipu:      { api_base: "https://open.bigmodel.cn/api/paas/v4",            model: "glm-4-flash" },
  deepseek:   { api_base: "https://api.deepseek.com/v1",                     model: "deepseek-chat" },
  ollama:     { api_base: "http://localhost:11434/v1",                       model: "llama3.2" },
};

const $ = (id) => document.getElementById(id);

const floatCircle  = $("float-circle");
const chatPanel    = $("chat-panel");
const chatHeader   = $("chat-header");
const messagesEl   = $("messages");
const msgInput     = $("msg-input");
const btnSend      = $("btn-send");
const btnClose     = $("btn-close");
const btnHide      = $("btn-hide");
const statusDot    = $("status-dot");
const statusText   = $("status-text");
const welcomeMsg   = $("welcome-msg");
const scrollBtn    = $("scroll-bottom-btn");

const wizard       = $("onboard-wizard");
const wizProvider  = $("wiz-provider");
const wizApiKey    = $("wiz-api-key");
const wizModel     = $("wiz-model");
const wizTest      = $("wiz-test");
const wizTestRes   = $("wiz-test-result");
const wizSave      = $("wiz-save");

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
    if (!historyLoaded) loadHistory(true);
  } else {
    document.body.className = "mode-float";
    cancelStream();
  }
}

async function openChat() {
  await invoke("set_chat");
  switchMode("chat");
  loadHistory(true);
}

// ── Listen for Rust mode-changed events (e.g. from hotkey) ──

listen("mode-changed", (event) => {
  switchMode(event.payload);
});

// ── Event listeners ──

btnClose.addEventListener("click", () => {
  invoke("hide_app");
});

btnHide.addEventListener("click", () => {
  invoke("hide_app");
});

// ── Input: textarea auto-resize ──

msgInput.addEventListener("input", () => {
  msgInput.style.height = "auto";
  msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + "px";
});

msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

btnSend.addEventListener("click", sendMessage);

// ── Welcome chips ──

welcomeMsg.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const text = chip.dataset.msg;
    if (text) {
      msgInput.value = text;
      sendMessage();
    }
  });
});

// ── Scroll-to-bottom button ──

messagesEl.addEventListener("scroll", () => {
  const nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 100;
  scrollBtn.style.display = nearBottom ? "none" : "block";
});

scrollBtn.addEventListener("click", scrollToBottom);

// ── History loading (scroll to top pagination) ──

let loadingHistory = false;

messagesEl.addEventListener("scroll", () => {
  if (messagesEl.scrollTop < 30 && historyOffset > 0 && !loadingHistory) {
    loadHistory(false);
  }
});

async function loadHistory(reset) {
  if (reset) {
    historyOffset = 0;
    historyLoaded = false;
    messagesEl.querySelectorAll(".msg").forEach((el) => el.remove());
  }
  if (loadingHistory) return;
  loadingHistory = true;

  try {
    const resp = await fetch(
      `${SERVER_URL}/api/history?session_id=${SESSION_ID}&limit=${HISTORY_PAGE}&offset=${historyOffset}`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!resp.ok) return;
    const data = await resp.json();
    if (!data.messages || data.messages.length === 0) {
      if (reset) welcomeMsg.style.display = "flex";
      return;
    }

    const prevScrollHeight = messagesEl.scrollHeight;
    const prevScrollTop = messagesEl.scrollTop;

    // Insert messages at the top (in reverse to maintain order)
    const fragment = document.createDocumentFragment();
    for (const msg of data.messages) {
      const el = document.createElement("div");
      el.className = `msg ${msg.role === "user" ? "user" : "bot"}`;
      if (msg.role === "user") {
        el.innerHTML = escapeHtml(msg.content);
      } else {
        el.innerHTML = renderMarkdown(msg.content);
      }
      fragment.appendChild(el);
    }
    messagesEl.insertBefore(fragment, messagesEl.firstChild);

    // Preserve scroll position
    if (reset) {
      scrollToBottom();
    } else {
      messagesEl.scrollTop = messagesEl.scrollHeight - prevScrollHeight + prevScrollTop;
    }

    historyOffset += data.messages.length;
    historyLoaded = true;
    welcomeMsg.style.display = "none";
  } catch {
    // silently fail
  }
  loadingHistory = false;
}

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
    statusText.textContent = "Server offline";
  }
}

// ── Send message ──

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || streaming) return;

  msgInput.value = "";
  msgInput.style.height = "auto";
  welcomeMsg.style.display = "none";
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
            botMsgEl.innerHTML = renderMarkdown(fullContent) + timestampHTML();
            scrollToBottom();
          } else if (event.type === "done") {
            botMsgEl.classList.remove("streaming");
            botMsgEl.innerHTML = renderMarkdown(event.content || fullContent) + timestampHTML();
            addCopyButton(botMsgEl);
            fullContent = event.content || fullContent;
          } else if (event.type === "error") {
            botMsgEl.innerHTML = `Error: ${event.content}`;
            botMsgEl.classList.remove("streaming");
          } else if (event.type === "tool_start") {
            addMessage(`→ ${event.name}...`, "system tool-call");
          } else if (event.type === "tool_done") {
            const sysMsgs = messagesEl.querySelectorAll(".msg.system.tool-call");
            if (sysMsgs.length > 0) {
              sysMsgs[sysMsgs.length - 1].remove();
            }
          }
        } catch {
          // skip malformed JSON
        }
      }
    }

    if (fullContent && botMsgEl.classList.contains("streaming")) {
      botMsgEl.classList.remove("streaming");
      botMsgEl.innerHTML = renderMarkdown(fullContent) + timestampHTML();
      addCopyButton(botMsgEl);
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

// ── Markdown Renderer ──

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return text.replace(/[&<>"']/g, (c) => map[c]);
}

function renderMarkdown(text) {
  if (!text) return "";

  let html = escapeHtml(text);

  // Code blocks (fenced) - must be done before inline code
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const langAttr = lang ? ` class="lang-${lang}"` : "";
    return `<pre><code${langAttr}>${code}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Unordered lists
  html = html.replace(/^[\s]*[-*][\s]+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/s, (match) => `<ul>${match}</ul>`);

  // Line breaks
  html = html.replace(/\n/g, "<br>");

  return html;
}

function timestampHTML() {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `<span class="msg-time">${time}</span>`;
}

function addCopyButton(msgEl) {
  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.textContent = "Copy";
  btn.addEventListener("click", () => {
    const text = msgEl.textContent.replace(msgEl.querySelector(".msg-time")?.textContent || "", "").trim();
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = "Copy"; }, 2000);
    });
  });
  msgEl.appendChild(btn);
}

// ── UI helpers ──

function addMessage(text, cls) {
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  if (text && !cls.includes("streaming")) {
    if (cls === "user") {
      el.innerHTML = escapeHtml(text) + timestampHTML();
    } else if (cls.startsWith("system")) {
      el.textContent = text;
    } else {
      el.innerHTML = renderMarkdown(text) + timestampHTML();
      addCopyButton(el);
    }
  } else if (cls.includes("streaming")) {
    // Empty bot message, content added during stream
  }
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

// ── First-run Onboard Wizard ──

function populateProviders() {
  for (const [key, val] of Object.entries(PROVIDERS)) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = key.charAt(0).toUpperCase() + key.slice(1);
    wizProvider.appendChild(opt);
  }
  wizProvider.value = "openrouter";
  wizModel.value = PROVIDERS.openrouter.model;
}

function onProviderChange() {
  const p = wizProvider.value;
  const info = PROVIDERS[p];
  if (info && !wizModel.dataset.userChanged) {
    wizModel.value = info.model;
  }
  validateWizard();
}

wizProvider.addEventListener("change", onProviderChange);

wizModel.addEventListener("input", () => {
  wizModel.dataset.userChanged = wizModel.value !== PROVIDERS[wizProvider.value]?.model ? "1" : "";
  validateWizard();
});

wizApiKey.addEventListener("input", validateWizard);

function validateWizard() {
  const hasKey = wizApiKey.value.trim().length > 0;
  wizTest.disabled = !hasKey;
  wizSave.disabled = !hasKey;
}

async function testConnection() {
  const provider = wizProvider.value;
  const info = PROVIDERS[provider];
  wizTest.disabled = true;
  wizTestRes.className = "wiz-test-result";
  wizTestRes.innerHTML = '<span class="wiz-spinner"></span>Testing...';

  try {
    const resp = await fetch(`${SERVER_URL}/api/config/test-llm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_key: wizApiKey.value.trim(),
        api_base: info.api_base,
        model: wizModel.value.trim() || info.model,
      }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await resp.json();
    if (data.ok) {
      wizTestRes.className = "wiz-test-result ok";
      wizTestRes.textContent = `Connected (${data.model})`;
    } else {
      wizTestRes.className = "wiz-test-result err";
      wizTestRes.textContent = data.error || "Connection failed";
    }
  } catch (err) {
    wizTestRes.className = "wiz-test-result err";
    wizTestRes.textContent = `Error: ${err.message}`;
  }
  wizTest.disabled = false;
}

wizTest.addEventListener("click", testConnection);

async function saveConfig() {
  const provider = wizProvider.value;
  const info = PROVIDERS[provider];
  const model = wizModel.value.trim() || info.model;

  wizSave.disabled = true;
  wizSave.textContent = "Saving...";

  try {
    const config = {
      active_provider: provider,
      providers: {
        [provider]: {
          api_key: wizApiKey.value.trim(),
          api_base: info.api_base,
        },
      },
      agents: {
        defaults: { model },
      },
    };

    const resp = await fetch(`${SERVER_URL}/api/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
      signal: AbortSignal.timeout(10000),
    });

    if (!resp.ok) {
      const data = await resp.json();
      wizTestRes.className = "wiz-test-result err";
      wizTestRes.textContent = data.error || "Save failed";
      wizSave.disabled = false;
      wizSave.textContent = "Save & Continue";
      return;
    }

    // Success — enter chat mode
    document.body.className = "mode-chat";
    await invoke("set_chat");
    switchMode("chat");
    loadHistory(true);
  } catch (err) {
    wizTestRes.className = "wiz-test-result err";
    wizTestRes.textContent = `Error: ${err.message}`;
    wizSave.disabled = false;
    wizSave.textContent = "Save & Continue";
  }
}

wizSave.addEventListener("click", saveConfig);

async function checkFirstRun() {
  populateProviders();
  // Retry fetching config (server may still be starting)
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const resp = await fetch(`${SERVER_URL}/api/config/raw`, {
        signal: AbortSignal.timeout(2000),
      });
      if (!resp.ok) throw new Error("Not ready");
      const cfg = await resp.json();
      if (cfg.active_provider && cfg.providers?.[cfg.active_provider]?.api_key) {
        return false;
      }
      break; // config responded but not configured → show wizard
    } catch {
      if (attempt < 5) {
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
  }
  document.body.className = "mode-onboard";
  return true;
}

// ── Init ──

async function init() {
  const isFirstRun = await checkFirstRun();
  if (isFirstRun) return;
  try {
    const mode = await invoke("get_mode");
    switchMode(mode);
  } catch {
    switchMode("floating");
  }
}

init();
