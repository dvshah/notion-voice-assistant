// Gemini + Notion Voice Assistant Client (with optional PIN lock)
let isListening = false;
let recognition = null;
let allDatabases = [];
let activeDbName = "Shopping List";
const sessionId = "web-" + Math.random().toString(36).slice(2, 10);
const PIN_STORAGE_KEY = "notion_voice_access_pin";

const micBtn = document.getElementById("micBtn");
const voiceStatusText = document.getElementById("voiceStatusText");
const voiceResponseBubble = document.getElementById("voiceResponseBubble");
const responseText = document.getElementById("responseText");
const actionsPills = document.getElementById("actionsPills");
const textInput = document.getElementById("textInput");
const dbTabsContainer = document.getElementById("dbTabsContainer");
const itemsContainer = document.getElementById("itemsContainer");
const geminiBadge = document.getElementById("geminiBadge");
const notionBadge = document.getElementById("notionBadge");
const pinOverlay = document.getElementById("pinOverlay");
const pinInput = document.getElementById("pinInput");
const pinError = document.getElementById("pinError");
const lockBtn = document.getElementById("lockBtn");

function getSavedPin() {
  return localStorage.getItem(PIN_STORAGE_KEY) || "";
}

async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const pin = getSavedPin();
  if (pin) headers["X-Access-Pin"] = pin;
  const res = await fetch(url, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    showPinScreen("Please enter your access PIN.");
    throw new Error("Unauthorized");
  }
  return res;
}

function showPinScreen(msg = "") {
  pinOverlay.classList.add("visible");
  pinError.textContent = msg;
  setTimeout(() => pinInput && pinInput.focus(), 50);
}

function hidePinScreen() {
  pinOverlay.classList.remove("visible");
  pinError.textContent = "";
}

async function submitPin() {
  const pin = pinInput.value.trim();
  if (!pin) {
    pinError.textContent = "Please enter your PIN.";
    return;
  }
  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    if (res.ok) {
      localStorage.setItem(PIN_STORAGE_KEY, pin);
      pinInput.value = "";
      hidePinScreen();
      lockBtn.style.display = "inline-flex";
      await Promise.all([fetchStatus(), fetchDatabases()]);
    } else {
      pinError.textContent = "Incorrect PIN. Try again.";
      pinInput.select();
    }
  } catch (err) {
    pinError.textContent = "Unable to reach server.";
  }
}

function lockApp() {
  localStorage.removeItem(PIN_STORAGE_KEY);
  showPinScreen("Locked. Enter PIN to continue.");
}

async function initAuthAndLoad() {
  try {
    const pin = getSavedPin();
    const res = await fetch("/api/auth/check", {
      headers: pin ? { "X-Access-Pin": pin } : {},
    });
    const data = await res.json();
    if (data.pin_required) {
      lockBtn.style.display = "inline-flex";
      if (!data.authorized) {
        showPinScreen("");
        return;
      }
    }
    await Promise.all([fetchStatus(), fetchDatabases()]);
  } catch (err) {
    console.error("Init error:", err);
  }
}

// Web Speech API setup
window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (window.SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add("listening");
    voiceStatusText.textContent = "Listening... Ask anything about your Notion lists";
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    voiceStatusText.textContent = `"${transcript}"`;
    executeVoiceCommand(transcript);
  };

  recognition.onerror = (event) => {
    console.error("Speech error:", event.error);
    isListening = false;
    micBtn.classList.remove("listening");
    voiceStatusText.textContent = "Couldn't catch that. Tap mic or type below.";
  };

  recognition.onend = () => {
    isListening = false;
    micBtn.classList.remove("listening");
  };
} else {
  voiceStatusText.textContent = "Type a command below or open in Chrome on Android for mic support.";
}

function speakText(text) {
  if ("speechSynthesis" in window && text) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.02;
    window.speechSynthesis.speak(utterance);
  }
}

function toggleListening() {
  if (!recognition) {
    alert("Browser speech recognition requires Chrome/Edge over HTTPS or localhost. You can type commands below!");
    return;
  }
  if (isListening) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch (e) {
      console.warn(e);
    }
  }
}

async function executeVoiceCommand(commandText) {
  voiceStatusText.textContent = "Thinking & syncing Notion...";
  voiceResponseBubble.style.display = "flex";
  responseText.textContent = "Processing with assistant...";
  actionsPills.innerHTML = "";

  try {
    const res = await apiFetch("/api/voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: commandText, session_id: sessionId }),
    });
    const data = await res.json();

    responseText.textContent = data.speech || "Done.";
    voiceStatusText.textContent = `You said: "${commandText}"`;

    const actions = data.actions_taken || [];
    if (actions.length > 0) {
      actionsPills.innerHTML = actions
        .map((a) => {
          const db = a.args?.database_name ? ` → ${a.args.database_name}` : "";
          return `<span class="action-chip">⚡ ${escapeHtml(a.tool)}${escapeHtml(db)}</span>`;
        })
        .join("");

      const lastDb = actions[actions.length - 1]?.args?.database_name;
      if (lastDb) activeDbName = lastDb;
    }

    if (data.speech) speakText(data.speech);
    await fetchDatabases();
  } catch (err) {
    if (err.message !== "Unauthorized") {
      console.error(err);
      responseText.textContent = "Failed to connect to the assistant server.";
      voiceStatusText.textContent = "Connection error.";
    }
  }
}

async function fetchStatus() {
  try {
    const res = await apiFetch("/api/status");
    const data = await res.json();

    if (data.gemini_enabled) {
      geminiBadge.className = "badge gemini";
      geminiBadge.innerHTML = `<span class="pulse-dot"></span> Gemini Live (${escapeHtml(data.gemini_model)})`;
    } else {
      geminiBadge.className = "badge mock";
      geminiBadge.innerHTML = `<span class="pulse-dot"></span> Local Parser (Add GEMINI_API_KEY)`;
    }

    if (data.notion_configured) {
      notionBadge.className = "badge live";
      notionBadge.innerHTML = `<span class="pulse-dot"></span> Notion Live Connected`;
    } else {
      notionBadge.className = "badge mock";
      notionBadge.innerHTML = `<span class="pulse-dot"></span> Notion Mock Workspace`;
    }
  } catch (err) {
    if (err.message !== "Unauthorized") console.error(err);
  }
}

async function fetchDatabases(forceRefresh = false) {
  try {
    const res = await apiFetch(`/api/databases?include_completed=true&refresh=${forceRefresh}`);
    const data = await res.json();
    allDatabases = data.databases || [];

    if (allDatabases.length > 0 && !allDatabases.some((d) => d.name === activeDbName)) {
      activeDbName = allDatabases[0].name;
    }
    renderDbTabs();
    renderActiveDbItems();
  } catch (err) {
    if (err.message !== "Unauthorized") console.error(err);
  }
}

function getDbIcon(name) {
  const lower = name.toLowerCase();
  if (lower.includes("shop") || lower.includes("grocer")) return "🛒";
  if (lower.includes("to-do") || lower.includes("todo") || lower.includes("task")) return "✅";
  if (lower.includes("note") || lower.includes("memo")) return "📝";
  return "📁";
}

function renderDbTabs() {
  dbTabsContainer.innerHTML = allDatabases
    .map(
      (db) => `
      <button class="db-tab ${db.name === activeDbName ? "active" : ""}" onclick="selectDatabase('${escapeQuotes(db.name)}')">
        <span>${getDbIcon(db.name)} ${escapeHtml(db.name)}</span>
        <span class="count-pill">${db.active_count}</span>
      </button>
    `
    )
    .join("");
}

function selectDatabase(name) {
  activeDbName = name;
  renderDbTabs();
  renderActiveDbItems();
}

function renderActiveDbItems() {
  if (allDatabases.length === 0) {
    itemsContainer.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:1.4rem 0.75rem;line-height:1.6;">
      <strong style="color:#f8fafc;">Notion is connected!</strong><br>
      No pages or databases are shared with your integration yet.<br>
      Open your <strong>Shopping List</strong> or <strong>To-Do List</strong> in Notion → tap <code>•••</code> → <strong>Connections</strong> → connect your integration, then tap <strong>↻ Sync</strong>.
    </div>`;
    return;
  }

  const db = allDatabases.find((d) => d.name === activeDbName);
  const items = db ? db.items : [];

  if (!items.length) {
    itemsContainer.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:1.4rem 0;">No items in ${escapeHtml(activeDbName)} yet.</div>`;
    return;
  }

  itemsContainer.innerHTML = items
    .map((it) => {
      const prioClass = it.priority ? `prio-${it.priority.toLowerCase()}` : "";
      const metaTags = [];
      if (it.priority) metaTags.push(`<span class="meta-tag ${prioClass}">${escapeHtml(it.priority)}</span>`);
      if (it.due_date) metaTags.push(`<span class="meta-tag">📅 ${escapeHtml(it.due_date)}</span>`);
      if (it.category) metaTags.push(`<span class="meta-tag">${escapeHtml(it.category)}</span>`);

      return `
      <div class="item-row ${it.completed ? "completed" : ""}">
        <div class="item-left">
          <input
            type="checkbox"
            class="item-checkbox"
            ${it.completed ? "checked" : ""}
            onchange="toggleItemDone('${escapeQuotes(activeDbName)}', '${escapeQuotes(it.id)}', this.checked)"
          />
          <div class="item-content">
            <span class="item-name">${escapeHtml(it.name)}</span>
            ${metaTags.length ? `<div class="item-meta">${metaTags.join("")}</div>` : ""}
            ${it.notes ? `<div class="item-notes">${escapeHtml(it.notes)}</div>` : ""}
          </div>
        </div>
        <button class="delete-btn" onclick="deleteItem('${escapeQuotes(it.id)}')" title="Delete">✕</button>
      </div>`;
    })
    .join("");
}

async function toggleItemDone(dbName, itemId, isChecked) {
  try {
    await apiFetch(`/api/databases/${encodeURIComponent(dbName)}/items/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: isChecked }),
    });
    await fetchDatabases();
  } catch (err) {
    if (err.message !== "Unauthorized") console.error(err);
  }
}

async function deleteItem(itemId) {
  try {
    await apiFetch(`/api/items/${encodeURIComponent(itemId)}`, { method: "DELETE" });
    await fetchDatabases();
  } catch (err) {
    if (err.message !== "Unauthorized") console.error(err);
  }
}

async function resetMemory() {
  try {
    await apiFetch(`/api/chat/reset?session_id=${encodeURIComponent(sessionId)}`, { method: "POST" });
    voiceStatusText.textContent = "Conversation memory cleared.";
    voiceResponseBubble.style.display = "none";
  } catch (err) {
    if (err.message !== "Unauthorized") console.error(err);
  }
}

function sendTextCommand() {
  const val = textInput.value.trim();
  if (val) {
    executeVoiceCommand(val);
    textInput.value = "";
  }
}

function handleInputKey(event) {
  if (event.key === "Enter") sendTextCommand();
}

function sendPreset(text) {
  executeVoiceCommand(text);
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((c) => (c.style.display = "none"));
  document.getElementById(`tab-btn-${tabName}`).classList.add("active");
  document.getElementById(`tab-content-${tabName}`).style.display = "block";
}

function escapeHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeQuotes(str) {
  return String(str).replace(/'/g, "\\'");
}

initAuthAndLoad();
