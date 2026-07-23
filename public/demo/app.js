const runBtn = document.getElementById("run-demo");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const credsEl = document.getElementById("demo-creds");
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const playBtn = document.getElementById("play-voice");
const downloadLink = document.getElementById("download-voice");

let chatSessionId = null;
let lastSpeakText = "";
let downloadUrl = null;
let busy = false;

function apiError(data, fallback) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  return fallback;
}

function demoDisabledMessage() {
  return (
    "Public demo is disabled. Set DEMO_ENABLED=true in .env and restart the server."
  );
}

function clearChat() {
  chatLog.innerHTML = "";
}

function appendChat(role, text) {
  const row = document.createElement("div");
  row.className = `chat-bubble ${role}`;
  row.innerHTML = `<span class="role">${role}</span><p></p>`;
  row.querySelector("p").textContent = text;
  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function playOnSpeakers(text) {
  lastSpeakText = text;
  playBtn.disabled = false;
  statusEl.textContent = "Playing on Mac speakers…";
  const res = await fetch("/api/v1/demo/hear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiError(data, `Hear failed (${res.status})`));
  statusEl.textContent = `Played on speakers (${data.bytes || "?"} bytes). Turn volume up if silent.`;

  // Optional download uses the same TTS once, only when user asks.
  downloadLink.classList.add("hidden");
  downloadLink.onclick = async (event) => {
    event.preventDefault();
    const speakRes = await fetch("/api/v1/demo/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!speakRes.ok) return;
    const buffer = await speakRes.arrayBuffer();
    const blob = new Blob([buffer], { type: "audio/wav" });
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = "assistant.wav";
    a.click();
  };
  downloadLink.classList.remove("hidden");
}

async function runDemo() {
  if (busy) return;
  busy = true;
  runBtn.disabled = true;
  chatSend.disabled = true;
  statusEl.textContent = "Running one-click sample call…";
  resultsEl.classList.add("hidden");
  clearChat();
  chatSessionId = null;
  try {
    const res = await fetch("/api/v1/demo/quickstart", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiError(data, res.statusText));

    document.getElementById("out-status").textContent = data.status;
    document.getElementById("out-e2e").textContent =
      data.e2e_ms != null ? `${Math.round(data.e2e_ms)} ms` : "—";
    document.getElementById("out-session").textContent = data.session_id || "—";
    resultsEl.classList.remove("hidden");

    chatSessionId = data.session_id || null;
    appendChat("user", data.user_transcript);
    appendChat("assistant", data.assistant_response || "(no reply)");
    if (data.assistant_response) await playOnSpeakers(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Demo failed: ${err.message}`;
  } finally {
    busy = false;
    runBtn.disabled = false;
    chatSend.disabled = false;
  }
}

async function sendChat(event) {
  event.preventDefault();
  if (busy) return;
  const message = chatInput.value.trim();
  if (!message) return;

  busy = true;
  chatSend.disabled = true;
  runBtn.disabled = true;
  chatInput.value = "";
  appendChat("user", message);
  statusEl.textContent = "Thinking…";

  try {
    const res = await fetch("/api/v1/demo/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: chatSessionId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiError(data, res.statusText));

    chatSessionId = data.session_id;
    appendChat("assistant", data.assistant_response);
    document.getElementById("out-status").textContent = "chat_turn_ok";
    document.getElementById("out-e2e").textContent =
      data.e2e_ms != null ? `${Math.round(data.e2e_ms)} ms` : "—";
    document.getElementById("out-session").textContent = data.session_id;
    resultsEl.classList.remove("hidden");

    await playOnSpeakers(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Chat failed: ${err.message}`;
    appendChat("system", `Error: ${err.message}`);
  } finally {
    busy = false;
    chatSend.disabled = false;
    runBtn.disabled = false;
    chatInput.focus();
  }
}

runBtn.addEventListener("click", runDemo);
chatForm.addEventListener("submit", sendChat);
playBtn.addEventListener("click", () => {
  if (!lastSpeakText) {
    statusEl.textContent = "No audio yet — send a message first.";
    return;
  }
  playOnSpeakers(lastSpeakText).catch((err) => {
    statusEl.textContent = `Play failed: ${err.message}`;
  });
});

async function loadDemoInfo() {
  try {
    const res = await fetch("/api/v1/demo/info");
    if (res.status === 404) {
      runBtn.disabled = true;
      chatSend.disabled = true;
      playBtn.disabled = true;
      statusEl.textContent = demoDisabledMessage();
      return;
    }
    if (!res.ok) return;
    const data = await res.json();
    if (credsEl && data.email && data.password_hint) {
      credsEl.textContent = `${data.email} / ${data.password_hint}`;
    }
  } catch {
    // ignore
  }
}

loadDemoInfo();
chatInput.focus();
