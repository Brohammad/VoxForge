const runBtn = document.getElementById("run-demo");
const micBtn = document.getElementById("mic-btn");
const trustLoopBtn = document.getElementById("trust-loop-btn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const citationsEl = document.getElementById("citations");
const inspectLinksEl = document.getElementById("inspect-links");
const openReplayEl = document.getElementById("open-replay");
const openInboxEl = document.getElementById("open-inbox");
const credsEl = document.getElementById("demo-creds");
const providerBadgeEl = document.getElementById("provider-badge");
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const playBtn = document.getElementById("play-voice");
const downloadLink = document.getElementById("download-voice");

const MAX_RECORD_MS = 15000;
const TARGET_SAMPLE_RATE = 16000;

let chatSessionId = null;
let lastSpeakText = "";
let downloadUrl = null;
let currentAudio = null;
let busy = false;
let talking = false;
let recordCtx = null;
let recordProc = null;
let recordSource = null;
let recordGain = null;
let recordStream = null;
let recordChunks = [];
let recordTimer = null;
let speechRec = null;
let liveTranscript = "";
let providersMode = "mock";

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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

function setBusy(value) {
  busy = value;
  runBtn.disabled = value || talking;
  chatSend.disabled = value || talking;
  if (trustLoopBtn) trustLoopBtn.disabled = value || talking;
  if (micBtn && !talking) micBtn.disabled = value;
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
  return row;
}

function stopCurrentAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
}

function showTurn(status, e2eMs, sessionId) {
  document.getElementById("out-status").textContent = status;
  document.getElementById("out-e2e").textContent =
    e2eMs != null ? `${Math.round(e2eMs)} ms` : "—";
  document.getElementById("out-session").textContent = sessionId || "—";
  resultsEl.classList.remove("hidden");
  if (sessionId && openReplayEl) {
    openReplayEl.href = `/dashboard#session=${sessionId}`;
    inspectLinksEl.classList.remove("hidden");
  }
}

function showCitations(citations, replayUrl, inboxUrl) {
  if (replayUrl && openReplayEl) openReplayEl.href = replayUrl;
  if (inboxUrl && openInboxEl) openInboxEl.href = inboxUrl;
  inspectLinksEl.classList.remove("hidden");
  if (!citationsEl) return;
  if (!citations || !citations.length) {
    citationsEl.classList.add("hidden");
    citationsEl.innerHTML = "";
    return;
  }
  const items = citations
    .map((c) => {
      const label = escapeHtml(c.citation_label || c.document_title || "Source");
      const excerpt = escapeHtml(c.excerpt || "");
      return `<li><strong>${label}</strong> — ${excerpt}</li>`;
    })
    .join("");
  citationsEl.innerHTML = `<h3>Citations</h3><ul>${items}</ul>`;
  citationsEl.classList.remove("hidden");
}

async function playInBrowser(text) {
  lastSpeakText = text;
  playBtn.disabled = false;
  statusEl.textContent = "Synthesizing voice…";
  stopCurrentAudio();

  const res = await fetch("/api/v1/demo/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(apiError(data, `Speak failed (${res.status})`));
  }

  const buffer = await res.arrayBuffer();
  const blob = new Blob([buffer], { type: "audio/wav" });
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(blob);

  currentAudio = new Audio(downloadUrl);
  currentAudio.addEventListener("ended", () => {
    statusEl.textContent = "Playback finished.";
  });
  statusEl.textContent = "Playing in your browser…";
  try {
    await currentAudio.play();
  } catch (playErr) {
    statusEl.textContent = `Tap Play voice — autoplay blocked (${playErr.message}).`;
  }

  downloadLink.href = downloadUrl;
  downloadLink.classList.remove("hidden");
}

function resampleTo16k(float32, inputRate) {
  if (inputRate === TARGET_SAMPLE_RATE) return float32;
  const ratio = inputRate / TARGET_SAMPLE_RATE;
  const outLen = Math.max(1, Math.round(float32.length / ratio));
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i += 1) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const i1 = Math.min(i0 + 1, float32.length - 1);
    const frac = src - i0;
    out[i] = float32[i0] * (1 - frac) + float32[i1] * frac;
  }
  return out;
}

function mergeFloat32(chunks) {
  let total = 0;
  for (const chunk of chunks) total += chunk.length;
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function encodeWav(float32, sampleRate) {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const dataSize = int16.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeStr = (off, str) => {
    for (let i = 0; i < str.length; i += 1) view.setUint8(off + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  new Uint8Array(buffer, 44).set(new Uint8Array(int16.buffer, int16.byteOffset, dataSize));
  return new Blob([buffer], { type: "audio/wav" });
}

function stopSpeechRecognition() {
  if (!speechRec) return;
  try {
    speechRec.onresult = null;
    speechRec.stop();
  } catch {
    // already stopped
  }
  speechRec = null;
}

function startSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;
  stopSpeechRecognition();
  liveTranscript = "";
  speechRec = new SpeechRecognition();
  speechRec.continuous = true;
  speechRec.interimResults = true;
  speechRec.lang = "en-US";
  speechRec.onresult = (event) => {
    let finalText = "";
    let interim = "";
    for (let i = 0; i < event.results.length; i += 1) {
      const piece = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += piece;
      else interim += piece;
    }
    liveTranscript = `${finalText} ${interim}`.trim();
    if (liveTranscript) statusEl.textContent = `Heard: ${liveTranscript}`;
  };
  speechRec.onerror = () => {};
  try {
    speechRec.start();
  } catch {
    // start() throws if already started
  }
}

function teardownRecorder() {
  if (recordTimer) {
    clearTimeout(recordTimer);
    recordTimer = null;
  }
  if (recordProc) {
    recordProc.onaudioprocess = null;
    try {
      recordProc.disconnect();
    } catch {
      // ignore
    }
    recordProc = null;
  }
  if (recordSource) {
    try {
      recordSource.disconnect();
    } catch {
      // ignore
    }
    recordSource = null;
  }
  if (recordGain) {
    try {
      recordGain.disconnect();
    } catch {
      // ignore
    }
    recordGain = null;
  }
  if (recordStream) {
    recordStream.getTracks().forEach((track) => track.stop());
    recordStream = null;
  }
  if (recordCtx) {
    recordCtx.close().catch(() => {});
    recordCtx = null;
  }
}

function resetMicButton() {
  talking = false;
  if (!micBtn) return;
  micBtn.dataset.recording = "false";
  micBtn.textContent = "Start talking";
  micBtn.disabled = busy;
}

async function startTalk() {
  if (busy || talking) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusEl.textContent = "Microphone requires HTTPS (or localhost) and a supported browser.";
    return;
  }
  talking = true;
  liveTranscript = "";
  recordChunks = [];
  micBtn.dataset.recording = "true";
  micBtn.textContent = "Stop & send";
  runBtn.disabled = true;
  chatSend.disabled = true;
  statusEl.textContent = "Listening… speak, then click Stop & send.";

  try {
    recordStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    recordCtx = new AudioContext();
    if (recordCtx.state === "suspended") await recordCtx.resume();
    recordSource = recordCtx.createMediaStreamSource(recordStream);
    recordProc = recordCtx.createScriptProcessor(4096, 1, 1);
    recordGain = recordCtx.createGain();
    recordGain.gain.value = 0;
    recordProc.onaudioprocess = (event) => {
      if (!talking) return;
      recordChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    };
    recordSource.connect(recordProc);
    recordProc.connect(recordGain);
    recordGain.connect(recordCtx.destination);
    startSpeechRecognition();
    recordTimer = setTimeout(() => {
      stopTalk().catch((err) => {
        statusEl.textContent = `Mic failed: ${err.message}`;
      });
    }, MAX_RECORD_MS);
  } catch (err) {
    teardownRecorder();
    resetMicButton();
    setBusy(false);
    statusEl.textContent = `Microphone blocked (${err.message}). Allow mic or type below.`;
  }
}

async function stopTalk() {
  if (!talking) return;
  talking = false;
  stopSpeechRecognition();
  const inputRate = recordCtx ? recordCtx.sampleRate : TARGET_SAMPLE_RATE;
  const chunks = recordChunks;
  teardownRecorder();
  micBtn.dataset.recording = "false";
  micBtn.textContent = "Start talking";

  const merged = mergeFloat32(chunks);
  const pcm = resampleTo16k(merged, inputRate);
  const hasAudio = pcm.length > TARGET_SAMPLE_RATE * 0.15;
  const transcript = liveTranscript.trim();
  if (!hasAudio && !transcript) {
    setBusy(false);
    statusEl.textContent = "Didn't catch any speech — try again or type a message.";
    return;
  }

  setBusy(true);
  statusEl.textContent = "Sending voice turn…";
  const userRow = appendChat("user", transcript || "(voice)");

  try {
    const form = new FormData();
    if (hasAudio) form.append("audio", encodeWav(pcm, TARGET_SAMPLE_RATE), "speech.wav");
    if (transcript) form.append("transcript", transcript);
    if (chatSessionId) form.append("session_id", chatSessionId);

    const res = await fetch("/api/v1/demo/voice", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiError(data, res.statusText));

    chatSessionId = data.session_id;
    const heard = data.user_message || transcript || "(voice)";
    userRow.querySelector("p").textContent = heard;
    appendChat("assistant", data.assistant_response);
    showTurn("voice_turn_ok", data.e2e_ms, data.session_id);
    if (data.stt_provider === "mock" && data.stt_source === "provider") {
      statusEl.textContent =
        "Mock STT does not decode speech. Chrome speech recognition or typed chat will use your words.";
    }
    if (data.assistant_response) await playInBrowser(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Voice failed: ${err.message}`;
    appendChat("system", `Error: ${err.message}`);
  } finally {
    setBusy(false);
  }
}

async function runTrustLoop() {
  if (busy || talking) return;
  setBusy(true);
  statusEl.textContent = "Seeding FAQ, citing it, and opening replay + handoff…";
  resultsEl.classList.add("hidden");
  if (citationsEl) {
    citationsEl.classList.add("hidden");
    citationsEl.innerHTML = "";
  }
  clearChat();
  chatSessionId = null;
  try {
    const res = await fetch("/api/v1/demo/trust-loop", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiError(data, res.statusText));

    showTurn(data.status, data.e2e_ms, data.session_id);
    showCitations(data.citations, data.replay_url, data.inbox_url);
    chatSessionId = data.session_id || null;
    appendChat("user", data.user_transcript);
    appendChat("assistant", data.assistant_response || "(no reply)");
    if (data.assistant_response) await playInBrowser(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Trust loop failed: ${err.message}`;
  } finally {
    setBusy(false);
  }
}

async function runDemo() {
  if (busy || talking) return;
  setBusy(true);
  statusEl.textContent = "Running one-click sample call…";
  resultsEl.classList.add("hidden");
  if (citationsEl) {
    citationsEl.classList.add("hidden");
    citationsEl.innerHTML = "";
  }
  clearChat();
  chatSessionId = null;
  try {
    const res = await fetch("/api/v1/demo/quickstart", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiError(data, res.statusText));

    showTurn(data.status, data.e2e_ms, data.session_id);
    chatSessionId = data.session_id || null;
    appendChat("user", data.user_transcript);
    appendChat("assistant", data.assistant_response || "(no reply)");
    if (data.assistant_response) await playInBrowser(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Demo failed: ${err.message}`;
  } finally {
    setBusy(false);
  }
}

async function sendChat(event) {
  event.preventDefault();
  if (busy || talking) return;
  const message = chatInput.value.trim();
  if (!message) return;

  setBusy(true);
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
    showTurn("chat_turn_ok", data.e2e_ms, data.session_id);
    await playInBrowser(data.assistant_response);
  } catch (err) {
    statusEl.textContent = `Chat failed: ${err.message}`;
    appendChat("system", `Error: ${err.message}`);
  } finally {
    setBusy(false);
    chatInput.focus();
  }
}

runBtn.addEventListener("click", runDemo);
if (trustLoopBtn) trustLoopBtn.addEventListener("click", runTrustLoop);
chatForm.addEventListener("submit", sendChat);
micBtn.addEventListener("click", () => {
  if (talking) stopTalk();
  else startTalk();
});
playBtn.addEventListener("click", () => {
  if (!lastSpeakText) {
    statusEl.textContent = "No audio yet — send a message first.";
    return;
  }
  playInBrowser(lastSpeakText).catch((err) => {
    statusEl.textContent = `Play failed: ${err.message}`;
  });
});

function renderProviderBadge(data) {
  if (!providerBadgeEl) return;
  const mode = data.providers_mode || "mock";
  providersMode = mode;
  const detail = `STT ${data.stt_provider} · LLM ${data.llm_provider} · TTS ${data.tts_provider}`;
  providerBadgeEl.textContent =
    mode === "mock"
      ? `Mock providers (${detail}) — latency is not production-realistic`
      : mode === "live"
        ? `Live providers (${detail})`
        : `Mixed providers (${detail})`;
  providerBadgeEl.dataset.mode = mode;
}

async function loadDemoInfo() {
  try {
    const res = await fetch("/api/v1/demo/info");
    if (res.status === 404) {
      runBtn.disabled = true;
      chatSend.disabled = true;
      playBtn.disabled = true;
      micBtn.disabled = true;
      if (trustLoopBtn) trustLoopBtn.disabled = true;
      statusEl.textContent = demoDisabledMessage();
      return;
    }
    if (!res.ok) return;
    const data = await res.json();
    renderProviderBadge(data);
    if (credsEl && data.email && data.password_hint) {
      credsEl.textContent = `${data.email} / ${data.password_hint}`;
    }
  } catch {
    // ignore
  }
}

if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
  micBtn.disabled = true;
  micBtn.title = "Microphone requires HTTPS (or localhost) and a supported browser.";
}

loadDemoInfo();
chatInput.focus();
