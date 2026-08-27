const API = "/api/v1";

if (typeof LivekitClient === "undefined") {
  document.getElementById("error-banner")?.classList.remove("hidden");
  const banner = document.getElementById("error-banner");
  if (banner) {
    banner.textContent =
      "LiveKit browser SDK failed to load. Hard-refresh the page (Cmd+Shift+R).";
  }
  throw new Error("LivekitClient global missing");
}

const { Room, RoomEvent, Track, ConnectionState } = LivekitClient;

let token = localStorage.getItem("voxforge_token") || "";
let room = null;
let sessionId = null;
let assistantBuffer = "";
let lastAssistantText = "";
let seenMessageIds = new Set();
let playedTexts = new Set();
let pollTimer = null;
let hearInFlight = false;
let liveAssistantEl = null;
let pttDown = false;
let callPhase = "idle";
let mediaRecorder = null;
let micChunks = [];
let assistantWavParts = []; // {text, blob} from /demo/hear
let currentAudio = null; // HTMLAudioElement for barge-in stop

const els = {
  tokenInput: document.getElementById("token-input"),
  identityInput: document.getElementById("identity-input"),
  nameInput: document.getElementById("name-input"),
  demoLoginBtn: document.getElementById("demo-login-btn"),
  connectBtn: document.getElementById("connect-btn"),
  disconnectBtn: document.getElementById("disconnect-btn"),
  dashboardLink: document.getElementById("dashboard-link"),
  pttBtn: document.getElementById("ptt-btn"),
  downloadRecordingBtn: document.getElementById("download-recording-btn"),
  errorBanner: document.getElementById("error-banner"),
  statusConnection: document.getElementById("status-connection"),
  statusSession: document.getElementById("status-session"),
  statusRoom: document.getElementById("status-room"),
  statusUrl: document.getElementById("status-url"),
  statusParticipants: document.getElementById("status-participants"),
  statusMic: document.getElementById("status-mic"),
  statusPhase: document.getElementById("status-phase"),
  latStt: document.getElementById("lat-stt"),
  latLlm: document.getElementById("lat-llm"),
  latTts: document.getElementById("lat-tts"),
  latE2e: document.getElementById("lat-e2e"),
  audioContainer: document.getElementById("audio-container"),
  eventLog: document.getElementById("event-log"),
  transcriptBox: document.getElementById("transcript-box"),
  playSpeakersBtn: document.getElementById("play-speakers-btn"),
};

els.tokenInput.value = token;
els.identityInput.value =
  localStorage.getItem("voxforge_identity") || `user-${crypto.randomUUID().slice(0, 8)}`;

function log(message) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}`;
  els.eventLog.textContent = `${line}\n${els.eventLog.textContent}`.slice(0, 8000);
}

function showError(msg) {
  els.errorBanner.textContent = msg;
  els.errorBanner.classList.remove("hidden");
}

function clearError() {
  els.errorBanner.classList.add("hidden");
}

function setStatus(key, value) {
  if (els[key]) els[key].textContent = value;
}

function setPhase(phase) {
  callPhase = phase;
  setStatus("statusPhase", phase);
}

function msLabel(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value))} ms`;
}

function updateLatency(metrics) {
  if (!metrics) return;
  if (els.latStt) els.latStt.textContent = msLabel(metrics.stt_ms);
  if (els.latLlm) els.latLlm.textContent = msLabel(metrics.llm_first_token_ms);
  if (els.latTts) els.latTts.textContent = msLabel(metrics.tts_first_byte_ms);
  if (els.latE2e) els.latE2e.textContent = msLabel(metrics.e2e_ms);
  log(
    `Latency STT=${msLabel(metrics.stt_ms)} LLM=${msLabel(metrics.llm_first_token_ms)} TTS=${msLabel(metrics.tts_first_byte_ms)} E2E=${msLabel(metrics.e2e_ms)}`,
  );
}

function updateParticipantCount() {
  if (!room) {
    setStatus("statusParticipants", "0");
    return;
  }
  setStatus("statusParticipants", String(room.remoteParticipants.size + 1));
}

function setDashboardLink(id) {
  if (!els.dashboardLink) return;
  if (!id) {
    els.dashboardLink.classList.add("hidden");
    return;
  }
  els.dashboardLink.href = `/dashboard#session=${id}`;
  els.dashboardLink.classList.remove("hidden");
}

function appendTranscript(role, text) {
  if (!els.transcriptBox || !text) return;
  liveAssistantEl = null;
  const row = document.createElement("div");
  row.className = `transcript-line ${role}`;
  row.textContent = `${role}: ${text}`;
  els.transcriptBox.appendChild(row);
  els.transcriptBox.scrollTop = els.transcriptBox.scrollHeight;
}

function updateLiveAssistant(text) {
  if (!els.transcriptBox) return;
  if (!liveAssistantEl) {
    liveAssistantEl = document.createElement("div");
    liveAssistantEl.className = "transcript-line assistant live";
    els.transcriptBox.appendChild(liveAssistantEl);
  }
  liveAssistantEl.textContent = `assistant: ${text}`;
  els.transcriptBox.scrollTop = els.transcriptBox.scrollHeight;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed.detail === "string") detail = parsed.detail;
      else if (parsed.detail) detail = JSON.stringify(parsed.detail);
    } catch {
      // keep
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function textKey(text) {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

function stopLocalPlayback() {
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch {
      // ignore
    }
    currentAudio = null;
  }
}

async function sendInterrupt() {
  if (!room) return;
  try {
    const payload = new TextEncoder().encode(JSON.stringify({ type: "interrupt" }));
    await room.localParticipant.publishData(payload, { reliable: true });
    log("Sent interrupt to agent");
  } catch (err) {
    log(`Interrupt send failed: ${err.message}`);
  }
}

async function playOnMacSpeakers(text, { force = false } = {}) {
  const cleaned = (text || "").trim();
  if (!cleaned) return;
  const key = textKey(cleaned);
  if (!force && playedTexts.has(key)) return;
  if (hearInFlight) return;

  playedTexts.add(key);
  lastAssistantText = cleaned;
  if (els.playSpeakersBtn) els.playSpeakersBtn.disabled = false;

  hearInFlight = true;
  setPhase("speaking");
  log("Playing assistant in the browser…");
  try {
    // Prefer browser WAV playback (can interrupt) + server afplay for reliability.
    const res = await fetch(`${API}/demo/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cleaned }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `speak ${res.status}`);
    }
    const buffer = await res.arrayBuffer();
    const blob = new Blob([buffer], { type: "audio/wav" });
    assistantWavParts.push({ text: cleaned, blob });
    if (els.downloadRecordingBtn) els.downloadRecordingBtn.disabled = false;

    stopLocalPlayback();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    audio.playsInline = true;
    try {
      await audio.play();
      log(`Browser WAV playing (${buffer.byteLength} bytes)`);
    } catch (playErr) {
      log(`Browser play blocked (${playErr.message}); falling back to afplay`);
      await fetch(`${API}/demo/hear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: cleaned }),
      });
    }
  } catch (err) {
    playedTexts.delete(key);
    log(`Playback failed: ${err.message}`);
  } finally {
    hearInFlight = false;
    if (room) setPhase(pttDown ? "talking" : "listening (hold Space)");
  }
}

async function demoLogin() {
  clearError();
  els.demoLoginBtn.disabled = true;
  try {
    const info = await fetch(`${API}/demo/info`).then((r) => {
      if (!r.ok) throw new Error("Demo account is disabled");
      return r.json();
    });
    const data = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: info.email, password: info.password_hint }),
    }).then(async (r) => {
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `login ${r.status}`);
      return body;
    });
    token = data.access_token;
    els.tokenInput.value = token;
    localStorage.setItem("voxforge_token", token);
    log(`Logged in as ${info.email}`);
    setPhase("authenticated");
  } catch (err) {
    showError(err.message);
    log(`Demo login failed: ${err.message}`);
  } finally {
    els.demoLoginBtn.disabled = false;
  }
}

async function setMic(enabled) {
  if (!room) return;
  try {
    await room.localParticipant.setMicrophoneEnabled(enabled);
    setStatus("statusMic", enabled ? "live" : "muted (PTT)");
    if (els.pttBtn) {
      els.pttBtn.classList.toggle("active", enabled);
      els.pttBtn.textContent = enabled ? "Release to send" : "Hold to talk";
    }
  } catch (err) {
    log(`Mic toggle failed: ${err.message}`);
  }
}

async function pttStart(event) {
  if (event) event.preventDefault();
  if (!room || pttDown) return;
  pttDown = true;

  // Barge-in if agent is speaking.
  if (
    callPhase.includes("speaking") ||
    callPhase === "generating" ||
    hearInFlight
  ) {
    stopLocalPlayback();
    await sendInterrupt();
  }

  setPhase("talking");
  await setMic(true);
  log("PTT down — speak now");
}

async function pttEnd(event) {
  if (event) event.preventDefault();
  if (!room || !pttDown) return;
  pttDown = false;
  await new Promise((r) => setTimeout(r, 350));
  await setMic(false);
  setPhase("thinking");
  log("PTT up — waiting for agent reply");
}

async function startMicRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micChunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) micChunks.push(ev.data);
    };
    mediaRecorder.start(1000);
    log("Mic recording started");
  } catch (err) {
    log(`Mic recording unavailable: ${err.message}`);
  }
}

function stopMicRecording() {
  return new Promise((resolve) => {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      resolve(null);
      return;
    }
    mediaRecorder.onstop = () => {
      const blob = new Blob(micChunks, { type: "audio/webm" });
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      mediaRecorder = null;
      resolve(blob);
    };
    mediaRecorder.stop();
  });
}

async function downloadCallAudio() {
  const micBlob = await stopMicRecording();
  // Restart recording if still connected
  if (room) startMicRecording();

  if (!assistantWavParts.length && !micBlob) {
    log("Nothing to download yet");
    return;
  }

  // Download mic webm
  if (micBlob) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(micBlob);
    a.download = `voxforge-mic-${sessionId || "call"}.webm`;
    a.click();
  }
  // Download each assistant WAV (and latest as primary)
  const last = assistantWavParts[assistantWavParts.length - 1];
  if (last) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(last.blob);
    a.download = `voxforge-assistant-${sessionId || "call"}.wav`;
    a.click();
  }
  // Also zip-less: download all assistant turns
  assistantWavParts.forEach((part, i) => {
    if (part === last) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(part.blob);
    a.download = `voxforge-assistant-turn-${i + 1}.wav`;
    a.click();
  });
  log("Download started (mic webm + assistant wavs)");
}

async function seedSeenMessages() {
  if (!sessionId) return;
  try {
    const data = await api(`/sessions/${sessionId}/messages?limit=50`);
    for (const msg of data.messages || []) {
      seenMessageIds.add(msg.id || `${msg.role}:${msg.content}`);
    }
  } catch {
    // ignore
  }
}

async function pollSessionMessages() {
  if (!sessionId || !token || hearInFlight) return;
  try {
    const data = await api(`/sessions/${sessionId}/messages?limit=50`);
    for (const msg of data.messages || []) {
      const id = msg.id || `${msg.role}:${msg.content}:${msg.created_at || ""}`;
      if (seenMessageIds.has(id)) continue;
      seenMessageIds.add(id);
      const role = (msg.role || "").toLowerCase();
      const content = (msg.content || "").trim();
      if (!content) continue;
      if (role === "user") {
        appendTranscript("user", content);
        setPhase("thinking");
        log(`You: ${content}`);
      } else if (role === "assistant") {
        appendTranscript("assistant", content);
        log(`Agent: ${content}`);
        await playOnMacSpeakers(content);
      }
    }
  } catch {
    // transient
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(pollSessionMessages, 750);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function attachAudioTrack(track, participantIdentity) {
  if (els.audioContainer.querySelector(`[data-participant="${CSS.escape(participantIdentity)}"]`)) {
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "audio-track";
  wrap.dataset.participant = participantIdentity;

  const label = document.createElement("span");
  label.className = "audio-label";
  label.textContent = participantIdentity;

  const audioEl = track.attach();
  audioEl.autoplay = true;
  audioEl.playsInline = true;
  audioEl.muted = false;
  audioEl.controls = true;
  audioEl.volume = 1;

  const unmuteBtn = document.createElement("button");
  unmuteBtn.type = "button";
  unmuteBtn.className = "btn";
  unmuteBtn.textContent = "Unmute / Play agent";
  unmuteBtn.addEventListener("click", () => {
    audioEl.muted = false;
    audioEl.play().catch((err) => log(`Play failed: ${err.message}`));
  });

  wrap.appendChild(label);
  wrap.appendChild(unmuteBtn);
  wrap.appendChild(audioEl);
  els.audioContainer.appendChild(wrap);
  log(`Subscribed to WebRTC audio from ${participantIdentity}`);
  audioEl.play().catch(() => {});
}

function attachExistingRemoteAudio(activeRoom) {
  activeRoom.remoteParticipants.forEach((participant) => {
    participant.trackPublications.forEach((pub) => {
      if (pub.track && pub.kind === Track.Kind.Audio) {
        attachAudioTrack(pub.track, participant.identity);
      }
    });
  });
}

function detachParticipantTracks(participantIdentity) {
  els.audioContainer
    .querySelectorAll(`[data-participant="${participantIdentity}"]`)
    .forEach((el) => el.remove());
}

function handleAgentPayload(payload) {
  if (!payload || typeof payload !== "object") return;

  if (payload.type === "transcript") {
    if (payload.partial) setPhase("talking");
    else if (payload.text) {
      appendTranscript("user", payload.text);
      setPhase("thinking");
      log(`You: ${payload.text}`);
    }
  }

  if (payload.type === "response" && payload.token) {
    assistantBuffer += payload.token;
    updateLiveAssistant(assistantBuffer);
    setPhase("generating");
  }

  if (payload.type === "metric") {
    updateLatency(payload);
    const text = assistantBuffer.trim();
    assistantBuffer = "";
    liveAssistantEl = null;
    if (text) {
      appendTranscript("assistant", text);
      log(`Agent: ${text}`);
      playOnMacSpeakers(text);
    }
  }

  if (payload.type === "interrupted") {
    stopLocalPlayback();
    setPhase("interrupted");
    log("Agent interrupted");
  }

  if (payload.type === "error") {
    setPhase("error");
    log(`Agent error: ${payload.code || ""} ${payload.message || ""}`);
  }
}

function wireRoomEvents(activeRoom) {
  activeRoom.on(RoomEvent.ConnectionStateChanged, (state) => {
    setStatus("statusConnection", state);
    log(`Connection state: ${state}`);
  });

  activeRoom.on(RoomEvent.ParticipantConnected, (participant) => {
    log(`Participant joined: ${participant.identity}`);
    updateParticipantCount();
    attachExistingRemoteAudio(activeRoom);
  });

  activeRoom.on(RoomEvent.ParticipantDisconnected, (participant) => {
    detachParticipantTracks(participant.identity);
    log(`Participant left: ${participant.identity}`);
    updateParticipantCount();
  });

  activeRoom.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
    if (track.kind === Track.Kind.Audio) attachAudioTrack(track, participant.identity);
  });

  activeRoom.on(RoomEvent.TrackUnsubscribed, (track, _pub, participant) => {
    track.detach().forEach((el) => el.remove());
    detachParticipantTracks(participant.identity);
  });

  activeRoom.on(RoomEvent.DataReceived, (payload, participant) => {
    try {
      const text = typeof payload === "string" ? payload : new TextDecoder().decode(payload);
      handleAgentPayload(JSON.parse(text));
    } catch (err) {
      log(`Bad data message from ${participant?.identity || "agent"}: ${err.message}`);
    }
  });

  activeRoom.on(RoomEvent.Disconnected, (reason) => {
    log(`Disconnected${reason ? `: ${reason}` : ""}`);
    setPhase("idle");
    cleanupUi();
  });
}

function cleanupUi() {
  els.connectBtn.disabled = false;
  els.disconnectBtn.disabled = true;
  if (els.pttBtn) els.pttBtn.disabled = true;
  setStatus("statusMic", "off");
  setStatus("statusConnection", "idle");
  updateParticipantCount();
}

async function connect() {
  clearError();
  token = els.tokenInput.value.trim();
  const identity = els.identityInput.value.trim();
  const name = els.nameInput.value.trim() || identity;

  if (!token) {
    showError("Click “Use demo account” or log in first.");
    return;
  }
  if (!identity) {
    showError("Participant identity is required.");
    return;
  }

  localStorage.setItem("voxforge_token", token);
  localStorage.setItem("voxforge_identity", identity);

  els.connectBtn.disabled = true;
  setStatus("statusConnection", "connecting");
  setPhase("connecting");
  log("Creating WebRTC session…");
  assistantBuffer = "";
  liveAssistantEl = null;
  playedTexts = new Set();
  seenMessageIds = new Set();
  assistantWavParts = [];
  pttDown = false;

  try {
    const session = await api("/sessions", {
      method: "POST",
      body: JSON.stringify({ transport_type: "webrtc" }),
    });
    sessionId = session.session_id;
    setStatus("statusSession", sessionId);
    setDashboardLink(sessionId);
    log(`Session created: ${sessionId}`);

    const lk = await api(`/livekit/sessions/${sessionId}/token`, {
      method: "POST",
      body: JSON.stringify({
        participant_identity: identity,
        participant_name: name,
      }),
    });

    setStatus("statusRoom", lk.room_name);
    setStatus("statusUrl", lk.livekit_url);
    log(`Joining ${lk.room_name} via ${lk.livekit_url}`);

    room = new Room({ adaptiveStream: true, dynacast: true });
    wireRoomEvents(room);

    await room.connect(lk.livekit_url, lk.token, {
      peerConnectionTimeout: 20000,
      websocketTimeout: 20000,
    });
    await room.localParticipant.setMicrophoneEnabled(false);
    attachExistingRemoteAudio(room);
    await startMicRecording();

    setStatus("statusMic", "muted (PTT)");
    els.disconnectBtn.disabled = false;
    if (els.pttBtn) {
      els.pttBtn.disabled = false;
      els.pttBtn.textContent = "Hold to talk";
    }
    updateParticipantCount();
    await seedSeenMessages();
    startPolling();

    await playOnMacSpeakers("Connected. Hold space and speak when ready.", { force: true });
    setPhase("listening (hold Space)");
    log("Ready — hold Space to talk; start talking while agent speaks to interrupt.");
  } catch (err) {
    const msg = String(err.message || err);
    showError(msg);
    log(`Error: ${msg}`);
    setPhase("error");
    await disconnect();
  }
}

async function disconnect() {
  stopPolling();
  pttDown = false;
  stopLocalPlayback();
  els.disconnectBtn.disabled = true;
  if (els.pttBtn) els.pttBtn.disabled = true;
  const endedSession = sessionId;
  await stopMicRecording();
  if (room) {
    if (room.state !== ConnectionState.Disconnected) await room.disconnect();
    room = null;
  }
  els.audioContainer.innerHTML = "";
  sessionId = null;
  setStatus("statusSession", "—");
  setStatus("statusRoom", "—");
  setStatus("statusUrl", "—");
  setPhase("idle");
  if (endedSession) setDashboardLink(endedSession);
  cleanupUi();
  log("Session ended — use Download call audio if you want the recordings.");
}

els.demoLoginBtn?.addEventListener("click", demoLogin);
els.connectBtn.addEventListener("click", connect);
els.disconnectBtn.addEventListener("click", disconnect);
els.playSpeakersBtn?.addEventListener("click", () => {
  if (!lastAssistantText) return log("No assistant text yet.");
  playOnMacSpeakers(lastAssistantText, { force: true });
});
els.downloadRecordingBtn?.addEventListener("click", downloadCallAudio);

if (els.pttBtn) {
  els.pttBtn.addEventListener("pointerdown", pttStart);
  els.pttBtn.addEventListener("pointerup", pttEnd);
  els.pttBtn.addEventListener("pointerleave", pttEnd);
  els.pttBtn.addEventListener("pointercancel", pttEnd);
}

window.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || event.repeat) return;
  if (event.target && ["INPUT", "TEXTAREA"].includes(event.target.tagName)) return;
  pttStart(event);
});
window.addEventListener("keyup", (event) => {
  if (event.code !== "Space") return;
  pttEnd(event);
});

if (!token) {
  fetch(`${API}/demo/info`)
    .then((r) => (r.ok ? r.json() : null))
    .then((info) => {
      if (info?.email) log(`Tip: click “Use demo account” (${info.email}) then Start.`);
    })
    .catch(() => {});
}
