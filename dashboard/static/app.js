const API = "/api/v1/dashboard";
let token = localStorage.getItem("voxforge_token") || "";
/** True after a successful /me or dashboard fetch (cookie sessions are HttpOnly). */
let sessionOk = false;
let trendDays = Number(localStorage.getItem("voxforge_trend_days") || 7);
let orgId = null;

const els = {
  loginEmail: document.getElementById("login-email"),
  loginPassword: document.getElementById("login-password"),
  loginBtn: document.getElementById("login-btn"),
  logoutBtn: document.getElementById("logout-btn"),
  registerToggleBtn: document.getElementById("register-toggle-btn"),
  registerPanel: document.getElementById("register-panel"),
  registerForm: document.getElementById("register-form"),
  registerCancelBtn: document.getElementById("register-cancel-btn"),
  registerStatus: document.getElementById("register-status"),
  tokenInput: document.getElementById("token-input"),
  connectBtn: document.getElementById("connect-btn"),
  authStatus: document.getElementById("auth-status"),
  errorBanner: document.getElementById("error-banner"),
  overviewCards: document.getElementById("overview-cards"),
  voiceKpiCards: document.getElementById("voice-kpi-cards"),
  sessionsBody: document.getElementById("sessions-body"),
  latencyChart: document.getElementById("latency-chart"),
  evalSummary: document.getElementById("eval-summary"),
  evalMetrics: document.getElementById("eval-metrics"),
  outcomesTrendChart: document.getElementById("outcomes-trend-chart"),
  outcomesTrendTitle: document.getElementById("outcomes-trend-title"),
  activityList: document.getElementById("activity-list"),
  pageTitle: document.getElementById("page-title"),
  onboardingStatus: document.getElementById("onboarding-status"),
  onboardingJson: document.getElementById("onboarding-json"),
  wizardDismissBtn: document.getElementById("wizard-dismiss-btn"),
  wizardProgress: document.getElementById("wizard-progress"),
  wizardAuthStatus: document.getElementById("wizard-auth-status"),
  wizardInviteForm: document.getElementById("wizard-invite-form"),
  wizardInviteToken: document.getElementById("wizard-invite-token"),
  wizardInviteName: document.getElementById("wizard-invite-name"),
  wizardInvitePassword: document.getElementById("wizard-invite-password"),
  wizardInviteStatus: document.getElementById("wizard-invite-status"),
  wizardPresets: document.getElementById("wizard-presets"),
  wizardPresetStatus: document.getElementById("wizard-preset-status"),
  wizardKnowledgeForm: document.getElementById("wizard-knowledge-form"),
  wizardCollectionName: document.getElementById("wizard-collection-name"),
  wizardKnowledgeFile: document.getElementById("wizard-knowledge-file"),
  wizardKnowledgeStatus: document.getElementById("wizard-knowledge-status"),
  wizardSampleStatus: document.getElementById("wizard-sample-status"),
  wizardCompleteStatus: document.getElementById("wizard-complete-status"),
  wizardReplaySummary: document.getElementById("wizard-replay-summary"),
  wizardBackBtn: document.getElementById("wizard-back-btn"),
  wizardNextBtn: document.getElementById("wizard-next-btn"),
  wizardOpenReplayBtn: document.getElementById("wizard-open-replay-btn"),
  wizardOpenOverviewBtn: document.getElementById("wizard-open-overview-btn"),
  alertsSummary: document.getElementById("alerts-summary"),
  alertsList: document.getElementById("alerts-list"),
  replaySessionInput: document.getElementById("replay-session-input"),
  replayLoadBtn: document.getElementById("replay-load-btn"),
  replayOutcome: document.getElementById("replay-outcome"),
  replayExplanations: document.getElementById("replay-explanations"),
  replayTimeline: document.getElementById("replay-timeline"),
  policyActive: document.getElementById("policy-active"),
  policyPresets: document.getElementById("policy-presets"),
  policyVersionsBody: document.getElementById("policy-versions-body"),
  ssoOrg: document.getElementById("sso-org"),
  ssoConnectionsBody: document.getElementById("sso-connections-body"),
  ssoCreateForm: document.getElementById("sso-create-form"),
  ssoProviderType: document.getElementById("sso-provider-type"),
  ssoIdpEntityId: document.getElementById("sso-idp-entity-id"),
  ssoIdpSsoUrl: document.getElementById("sso-idp-sso-url"),
  ssoIdpCert: document.getElementById("sso-idp-cert"),
  ssoSpEntityId: document.getElementById("sso-sp-entity-id"),
  ssoAcsUrl: document.getElementById("sso-acs-url"),
  ssoDefaultRole: document.getElementById("sso-default-role"),
  ssoRoleMapping: document.getElementById("sso-role-mapping"),
  ssoLoginPreview: document.getElementById("sso-login-preview"),
  apiKeysStatus: document.getElementById("api-keys-status"),
  apiKeysBody: document.getElementById("api-keys-body"),
  apiKeyCreateForm: document.getElementById("api-key-create-form"),
  apiKeyName: document.getElementById("api-key-name"),
  apiKeyCreatedSecret: document.getElementById("api-key-created-secret"),
  knowledgeStatus: document.getElementById("knowledge-status"),
  knowledgeRefreshBtn: document.getElementById("knowledge-refresh-btn"),
  knowledgeCollectionsBody: document.getElementById("knowledge-collections-body"),
  knowledgeCollectionForm: document.getElementById("knowledge-collection-form"),
  knowledgeCollectionName: document.getElementById("knowledge-collection-name"),
  knowledgeUploadForm: document.getElementById("knowledge-upload-form"),
  knowledgeUploadCollection: document.getElementById("knowledge-upload-collection"),
  knowledgeUploadTitle: document.getElementById("knowledge-upload-title"),
  knowledgeUploadFile: document.getElementById("knowledge-upload-file"),
  knowledgeUploadStatus: document.getElementById("knowledge-upload-status"),
  knowledgeUploadsBody: document.getElementById("knowledge-uploads-body"),
  knowledgeSearchForm: document.getElementById("knowledge-search-form"),
  knowledgeSearchQuery: document.getElementById("knowledge-search-query"),
  knowledgeSearchResults: document.getElementById("knowledge-search-results"),
  handoffsRefreshBtn: document.getElementById("handoffs-refresh-btn"),
  handoffsBody: document.getElementById("handoffs-body"),
  handoffContextSummary: document.getElementById("handoff-context-summary"),
  handoffContextJson: document.getElementById("handoff-context-json"),
};

let kbRecentUploads = [];
let kbPollTimer = null;
/** Signed replay token from #replay=…&token=… deep links (handoff URLs). */
let replayTokenFromHash = null;

const WIZARD_DISMISS_KEY = "voxforge_wizard_dismissed";
const WIZARD_STATE_KEY = "voxforge_wizard_state";
const WIZARD_DEFAULT_PRESET = "customer-support-deflection";

const HUBS = {
  talk: {
    label: "Talk",
    defaultSection: "overview",
    sections: {
      overview: "Overview",
      onboarding: "First Agent",
      sessions: "Sessions",
      replay: "Replay",
      latency: "Latency",
      evaluations: "Evaluations",
    },
  },
  knowledge: {
    label: "Knowledge",
    defaultSection: "knowledge",
    sections: { knowledge: "Knowledge Base" },
  },
  inbox: {
    label: "Inbox",
    defaultSection: "handoffs",
    sections: { handoffs: "Handoffs", alerts: "Alerts" },
  },
  settings: {
    label: "Settings",
    defaultSection: "policies",
    sections: {
      policies: "Policy Presets",
      sso: "SSO",
      "api-keys": "API Keys",
      activity: "Activity",
    },
  },
};

const SECTION_TO_HUB = Object.fromEntries(
  Object.entries(HUBS).flatMap(([hubId, hub]) =>
    Object.keys(hub.sections).map((section) => [section, hubId])
  )
);

const wizardState = {
  step: 1,
  presetSlug: WIZARD_DEFAULT_PRESET,
  collectionId: null,
  testSessionId: null,
};

function loadWizardStateFromStorage() {
  try {
    const saved = JSON.parse(localStorage.getItem(WIZARD_STATE_KEY) || "{}");
    if (saved.step) wizardState.step = saved.step;
    if (saved.presetSlug) wizardState.presetSlug = saved.presetSlug;
    if (saved.collectionId) wizardState.collectionId = saved.collectionId;
    if (saved.testSessionId) wizardState.testSessionId = saved.testSessionId;
  } catch {
    // ignore corrupt storage
  }
}

function saveWizardState() {
  localStorage.setItem(WIZARD_STATE_KEY, JSON.stringify(wizardState));
}

function isWizardDismissed() {
  return localStorage.getItem(WIZARD_DISMISS_KEY) === "1";
}

function dismissWizard() {
  localStorage.setItem(WIZARD_DISMISS_KEY, "1");
}

function hasCookieSession() {
  // Access JWT is HttpOnly — JS cannot read voxforge_access. CSRF cookie is the readable signal.
  return Boolean(readCookie("voxforge_csrf")) || Boolean(readCookie("voxforge_access"));
}

function isAuthenticated() {
  return Boolean(token) || sessionOk || hasCookieSession();
}

function setWizardStep(step) {
  wizardState.step = step;
  saveWizardState();
  document.querySelectorAll(".wizard-step").forEach((node) => node.classList.add("hidden"));
  const panel = document.getElementById(`wizard-step-${step}`);
  if (panel) {
    panel.classList.remove("hidden");
    panel.classList.add("active");
  }
  els.wizardProgress?.querySelectorAll(".wizard-progress-step").forEach((node) => {
    const n = Number(node.dataset.step);
    node.classList.toggle("active", n === step);
    node.classList.toggle("done", n < step);
  });
  if (els.wizardBackBtn) {
    els.wizardBackBtn.disabled = step <= 1;
  }
  if (els.wizardNextBtn) {
    els.wizardNextBtn.textContent = step >= 5 ? "Go to overview" : "Continue";
  }
  if (step === 2) {
    loadWizardPresets().catch((err) => showError(err.message));
  }
  if (step === 5) {
    renderWizardCompletion().catch((err) => showError(err.message));
  }
}

function renderWizardAuthStatus() {
  if (!els.wizardAuthStatus) return;
  if (isAuthenticated()) {
    els.wizardAuthStatus.textContent = orgId
      ? `Connected · organization ${shortId(orgId)}`
      : "Connected · loading organization…";
  } else {
    els.wizardAuthStatus.textContent = "Log in with email/password, register above, or accept an invite below.";
  }
}

async function registerAccount(event) {
  event.preventDefault();
  const email = document.getElementById("register-email")?.value.trim();
  const password = document.getElementById("register-password")?.value || "";
  const fullName = document.getElementById("register-full-name")?.value.trim();
  const orgName = document.getElementById("register-org-name")?.value.trim();
  if (!email || !password || !fullName || !orgName) {
    showError("Complete all registration fields.");
    return;
  }
  clearError();
  if (els.registerStatus) els.registerStatus.textContent = "Creating account…";
  const res = await fetch("/api/v1/auth/register", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName, org_name: orgName }),
  });
  const body = await res.text();
  if (!res.ok) {
    if (els.registerStatus) els.registerStatus.textContent = "";
    throw new Error(parseApiError(res.status, body));
  }
  token = "";
  orgId = null;
  localStorage.removeItem("voxforge_token");
  els.registerPanel?.classList.add("hidden");
  if (els.registerStatus) els.registerStatus.textContent = "Account created.";
  await refreshAll();
  await maybeOpenWizardAfterLogin();
}

async function acceptInvite(event) {
  event.preventDefault();
  const inviteToken = els.wizardInviteToken?.value.trim();
  const fullName = els.wizardInviteName?.value.trim();
  const password = els.wizardInvitePassword?.value || "";
  if (!inviteToken || !fullName || !password) {
    showError("Complete invite token, name, and password.");
    return;
  }
  clearError();
  if (els.wizardInviteStatus) els.wizardInviteStatus.textContent = "Accepting invite…";
  const res = await fetch("/api/v1/auth/invites/accept", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: inviteToken, password, full_name: fullName }),
  });
  const body = await res.text();
  if (!res.ok) {
    if (els.wizardInviteStatus) els.wizardInviteStatus.textContent = "";
    throw new Error(parseApiError(res.status, body));
  }
  token = "";
  orgId = null;
  localStorage.removeItem("voxforge_token");
  if (els.wizardInviteStatus) els.wizardInviteStatus.textContent = "Invite accepted — you are logged in.";
  await refreshAll();
  await maybeOpenWizardAfterLogin();
}

async function apiKeysApi(path, options = {}) {
  const res = await fetch(`/api/v1/api-keys${path}`, {
    credentials: "include",
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  if (res.status === 204) return null;
  return res.json();
}

function renderApiKeys(keys) {
  if (!els.apiKeysBody) return;
  els.apiKeysBody.innerHTML = (keys || []).map((key) => `
    <tr>
      <td>${escapeHtml(key.name)}</td>
      <td><code>${escapeHtml(key.key_prefix)}…</code></td>
      <td>${escapeHtml((key.scopes || []).join(", "))}</td>
      <td>${fmtDate(key.created_at)}</td>
      <td><button type="button" class="link-btn danger" data-revoke-key="${key.id}">Revoke</button></td>
    </tr>
  `).join("") || "<tr><td colspan='5'>No API keys yet</td></tr>";

  els.apiKeysBody.querySelectorAll("[data-revoke-key]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm("Revoke this API key?")) return;
      try {
        clearError();
        await apiKeysApi(`/${btn.dataset.revokeKey}`, { method: "DELETE" });
        await loadApiKeys();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

async function loadApiKeys() {
  await ensureOrgId();
  if (els.apiKeysStatus) els.apiKeysStatus.textContent = `Organization ${orgId}`;
  const keys = await apiKeysApi("");
  renderApiKeys(keys);
  if (els.apiKeyCreatedSecret) {
    els.apiKeyCreatedSecret.classList.add("hidden");
    els.apiKeyCreatedSecret.textContent = "";
  }
}

function renderWizardPresets(presets) {
  if (!els.wizardPresets) return;
  const list = presets || [];
  els.wizardPresets.innerHTML = list.map((preset) => `
    <article class="preset-card ${preset.slug === wizardState.presetSlug ? "selected" : ""}" data-wizard-preset="${escapeHtml(preset.slug)}">
      <div>
        <span class="preset-source">${escapeHtml(preset.source)}</span>
        <h3>${escapeHtml(preset.name)}</h3>
      </div>
      <p class="preset-description">${escapeHtml(preset.description)}</p>
      <div class="preset-thresholds">orchestrator=${escapeHtml(preset.orchestrator_config?.mode || "single")} · ${escapeHtml(renderPolicyThresholds(preset.eval_thresholds))}</div>
    </article>
  `).join("") || "<p class='card-sub'>No presets available.</p>";

  els.wizardPresets.querySelectorAll("[data-wizard-preset]").forEach((card) => {
    card.addEventListener("click", () => {
      wizardState.presetSlug = card.dataset.wizardPreset;
      saveWizardState();
      els.wizardPresets.querySelectorAll(".preset-card").forEach((node) => {
        node.classList.toggle("selected", node.dataset.wizardPreset === wizardState.presetSlug);
      });
      if (els.wizardPresetStatus) {
        els.wizardPresetStatus.textContent = `Selected: ${wizardState.presetSlug}`;
      }
    });
  });
}

async function loadWizardPresets() {
  const [presets, active] = await Promise.all([
    agentConfigApi("/presets"),
    agentConfigApi("/active"),
  ]);
  renderWizardPresets(presets);
  if (els.wizardPresetStatus) {
    if (active) {
      els.wizardPresetStatus.textContent = `Active config: v${active.version} · ${active.label}`;
    } else {
      els.wizardPresetStatus.textContent = `Selected: ${wizardState.presetSlug}`;
    }
  }
}

async function wizardApplyPreset() {
  const slug = wizardState.presetSlug || WIZARD_DEFAULT_PRESET;
  await agentConfigApi(`/presets/${slug}/apply`, {
    method: "POST",
    body: JSON.stringify({ change_note: "Applied from first-agent wizard" }),
  });
  wizardState.presetSlug = slug;
  saveWizardState();
  if (els.wizardPresetStatus) {
    els.wizardPresetStatus.textContent = `Applied preset ${slug}`;
  }
}

async function wizardUploadKnowledge() {
  const name = els.wizardCollectionName?.value.trim() || "Support Docs";
  const file = els.wizardKnowledgeFile?.files?.[0];
  if (!file) {
    throw new Error("Choose a document to upload");
  }

  if (els.wizardKnowledgeStatus) {
    els.wizardKnowledgeStatus.textContent = "Creating collection…";
  }

  let collectionId = wizardState.collectionId;
  if (!collectionId) {
    const collections = await knowledgeApi("/collections");
    const existing = (collections || []).find((item) => item.name === name);
    if (existing) {
      collectionId = existing.id;
    } else {
      const created = await knowledgeApi("/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      collectionId = created.id;
    }
    wizardState.collectionId = collectionId;
    saveWizardState();
  }

  if (els.wizardKnowledgeStatus) {
    els.wizardKnowledgeStatus.textContent = `Uploading ${file.name}…`;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", file.name);
  const result = await knowledgeApi(`/collections/${collectionId}/documents`, {
    method: "POST",
    body: formData,
  });

  await syncKnowledgeDocumentsFromServer();
  scheduleKnowledgePolling();

  if (els.wizardKnowledgeStatus) {
    els.wizardKnowledgeStatus.textContent = "Processing document…";
  }

  for (let attempt = 0; attempt < 30; attempt += 1) {
    await refreshKnowledgeUploadStatuses();
    const latest = kbRecentUploads.find((item) => item.document_id === result.document_id);
    const status = latest?.status || result.status;
    if (status === "ready" || status === "indexed" || status === "completed") {
      if (els.wizardKnowledgeStatus) {
        els.wizardKnowledgeStatus.textContent = `Indexed ${file.name}`;
      }
      return;
    }
    if (status === "failed" || status === "error") {
      throw new Error(latest?.error_message || "Document indexing failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  if (els.wizardKnowledgeStatus) {
    els.wizardKnowledgeStatus.textContent = `Uploaded ${file.name} · indexing may still be running`;
  }
}

async function wizardRunSampleCall() {
  if (els.wizardSampleStatus) {
    els.wizardSampleStatus.textContent = "Running sample call…";
  }
  const run = await callOnboarding("/run-sample-call");
  renderOnboardingStatus(run);
  if (run.status !== "test_call_passed") {
    throw new Error(`Sample call did not pass (${run.status || "unknown"})`);
  }
  wizardState.testSessionId = run.test_session_id;
  saveWizardState();
  if (els.wizardSampleStatus) {
    els.wizardSampleStatus.textContent = `Passed · session ${shortId(run.test_session_id)}`;
  }
  await refreshAll();
}

async function renderWizardCompletion() {
  const sessionId = wizardState.testSessionId;
  if (!sessionId) {
    if (els.wizardCompleteStatus) {
      els.wizardCompleteStatus.textContent = "Sample call passed.";
    }
    return;
  }
  if (els.wizardCompleteStatus) {
    els.wizardCompleteStatus.textContent = `Test call passed · session ${shortId(sessionId)}`;
  }
  try {
    const res = await fetch(`/api/v1/sessions/${sessionId}/replay`, {
      credentials: "include",
      headers: authHeaders(),
    });
    if (!res.ok) return;
    const replay = await res.json();
    const lines = (replay.messages || []).slice(-4).map(
      (msg) => `${msg.role}: ${(msg.content || "").slice(0, 120)}`,
    );
    if (els.wizardReplaySummary) {
      els.wizardReplaySummary.textContent = [
        replay.outcome
          ? `task_success=${replay.outcome.task_success} · intent=${replay.outcome.intent}`
          : "Outcome pending",
        lines.join(" · ") || "Open replay for full transcript",
      ].join("\n");
    }
  } catch {
    if (els.wizardReplaySummary) {
      els.wizardReplaySummary.textContent = "Open replay for transcript and metrics.";
    }
  }
}

async function inferWizardStepFromStatus() {
  if (!isAuthenticated()) return 1;
  try {
    const res = await fetch("/api/v1/onboarding/status", {
      credentials: "include",
      headers: authHeaders(),
    });
    if (!res.ok) return 2;
    const run = await res.json();
    renderOnboardingStatus(run);
    if (run?.status === "test_call_passed") {
      wizardState.testSessionId = run.test_session_id || wizardState.testSessionId;
      saveWizardState();
      return 5;
    }
    if (run?.status === "token_connected") return 3;
    if (run?.status === "started") return 2;
  } catch {
    return 2;
  }
  return 2;
}

async function initWizard(options = {}) {
  loadWizardStateFromStorage();
  renderWizardAuthStatus();
  if (options.resetStep) {
    const inferred = await inferWizardStepFromStatus();
    if (inferred > wizardState.step) {
      wizardState.step = inferred;
      saveWizardState();
    }
  }
  setWizardStep(wizardState.step);
}

async function maybeOpenWizardAfterLogin() {
  if (isWizardDismissed()) return;
  try {
    const step = await inferWizardStepFromStatus();
    if (step >= 5) return;
    showSection("onboarding");
    wizardState.step = step;
    saveWizardState();
    await initWizard();
  } catch {
    // non-fatal
  }
}

async function wizardStepForward() {
  clearError();
  const step = wizardState.step;
  if (step === 1) {
    if (!isAuthenticated()) {
      throw new Error("Log in or connect a token before continuing");
    }
    await ensureOrgId();
    renderWizardAuthStatus();
    await callOnboarding("/start");
    if (token) {
      await callOnboarding("/connect-token", { token_preview: token.slice(0, 8) });
    } else {
      await callOnboarding("/connect-token", { token_preview: "cookie-auth" });
    }
    await loadOnboardingStatus();
    setWizardStep(2);
    return;
  }
  if (step === 2) {
    await wizardApplyPreset();
    setWizardStep(3);
    return;
  }
  if (step === 3) {
    await wizardUploadKnowledge();
    setWizardStep(4);
    return;
  }
  if (step === 4) {
    await wizardRunSampleCall();
    setWizardStep(5);
    return;
  }
  dismissWizard();
  showSection("overview");
  await refreshAll();
}

function wizardStepBack() {
  if (wizardState.step <= 1) return;
  setWizardStep(wizardState.step - 1);
}


els.tokenInput.value = token;

function parseApiError(status, body) {
  if (!body) {
    if (status === 401) return "Authentication required. Log in or paste a valid JWT.";
    if (status === 403) return "You do not have permission for this action.";
    if (status === 404) return "The requested resource was not found.";
    return `Request failed (${status}).`;
  }
  try {
    const data = JSON.parse(body);
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    }
  } catch {
    // Fall through to raw body.
  }
  return body.length > 180 ? `${body.slice(0, 180)}…` : body;
}

function readCookie(name) {
  const prefix = `${name}=`;
  const parts = document.cookie.split(";").map((p) => p.trim());
  for (const part of parts) {
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.slice(prefix.length));
    }
  }
  return "";
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  } else {
    const csrf = readCookie("voxforge_csrf");
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
  }
  return headers;
}

async function api(path) {
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  return res.json();
}

async function agentConfigApi(path, options = {}) {
  const res = await fetch(`/api/v1/agent-configs${path}`, {
    credentials: "include",
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  if (res.status === 204) return null;
  return res.json();
}

async function authApi(path) {
  const res = await fetch(`/api/v1/auth${path}`, {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  return res.json();
}

async function ensureOrgId() {
  if (orgId) return orgId;
  const me = await authApi("/me");
  orgId = me.org_id;
  return orgId;
}

function defaultAcsUrl(id) {
  return `${window.location.origin}/api/v1/orgs/${id}/sso/saml/acs`;
}

async function ssoApi(path, options = {}) {
  const id = await ensureOrgId();
  const res = await fetch(`/api/v1/orgs/${id}/sso/saml${path}`, {
    credentials: "include",
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  if (res.status === 204) return null;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

function showError(msg) {
  els.errorBanner.textContent = msg;
  els.errorBanner.classList.remove("hidden");
}

function clearError() {
  els.errorBanner.classList.add("hidden");
}

function setConnected(ok) {
  sessionOk = Boolean(ok);
  els.authStatus.textContent = ok ? "Connected" : "Not connected";
  els.authStatus.classList.toggle("connected", ok);
  els.logoutBtn?.classList.toggle("hidden", !ok);
  renderWizardAuthStatus();
}

async function loginWithPassword() {
  const email = els.loginEmail?.value.trim();
  const password = els.loginPassword?.value || "";
  if (!email || !password) {
    showError("Enter email and password to log in.");
    return;
  }
  clearError();
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await res.text();
  if (!res.ok) {
    throw new Error(parseApiError(res.status, body));
  }
  // Prefer HttpOnly cookie session; clear any prior localStorage JWT.
  token = "";
  orgId = null;
  els.tokenInput.value = "";
  localStorage.removeItem("voxforge_token");
  await refreshAll();
  await maybeOpenWizardAfterLogin();
}

async function logout() {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
  } catch {
    // ignore network errors on logout
  }
  token = "";
  orgId = null;
  els.tokenInput.value = "";
  localStorage.removeItem("voxforge_token");
  setConnected(false);
  clearError();
}

function card(label, value, sub = "") {
  return `<div class="card"><div class="card-label">${label}</div><div class="card-value">${value}</div>${sub ? `<div class="card-sub">${sub}</div>` : ""}</div>`;
}

function fmtMs(v) {
  return v != null ? `${Math.round(v)} ms` : "—";
}

function fmtScore(v) {
  return v != null ? v.toFixed(2) : "—";
}

function fmtCost(v) {
  return v != null ? `$${v.toFixed(4)}` : "—";
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function fmtPct(v) {
  return `${Math.round((v || 0) * 100)}%`;
}

function shortId(id) {
  return id ? id.slice(0, 8) + "…" : "—";
}

function setTrendDays(days) {
  trendDays = days === 30 ? 30 : 7;
  localStorage.setItem("voxforge_trend_days", String(trendDays));
  document.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.days) === trendDays);
  });
  if (els.outcomesTrendTitle) {
    els.outcomesTrendTitle.textContent = `Outcome Trends (${trendDays}d)`;
  }
}

function kpiCard(label, value, sub = "", tone = "") {
  return `<div class="card voice-kpi-card ${tone}"><div class="card-label">${label}</div><div class="card-value">${value}</div>${sub ? `<div class="card-sub">${sub}</div>` : ""}</div>`;
}

function latencyLabel(metricName) {
  return ({
    stt_ms: "STT",
    llm_first_token_ms: "LLM first token",
    tts_first_byte_ms: "TTS first byte",
    e2e_ms: "End-to-end",
  }[metricName] || metricName.replace(/_/g, " "));
}

async function loadOverview() {
  const [d, outcomes, latencyBuckets] = await Promise.all([
    api("/overview"),
    api(`/outcomes?days=${trendDays}`),
    api("/latency"),
  ]);

  const bucketByName = Object.fromEntries((latencyBuckets || []).map((b) => [b.metric_name, b]));
  const avgCostPerTurn = d.total_evaluations > 0 && d.estimated_total_cost_usd != null
    ? d.estimated_total_cost_usd / d.total_evaluations
    : null;

  if (els.voiceKpiCards) {
    const latencyCards = ["e2e_ms", "stt_ms", "llm_first_token_ms", "tts_first_byte_ms"].map((name) => {
      const bucket = bucketByName[name];
      if (!bucket) {
        return kpiCard(latencyLabel(name), "—", "No samples yet");
      }
      return kpiCard(
        latencyLabel(name),
        fmtMs(bucket.avg_ms),
        `${bucket.sample_count} turns${bucket.p95_ms != null ? ` · p95 ${Math.round(bucket.p95_ms)} ms` : ""}`,
        name === "e2e_ms" ? "kpi-accent" : "",
      );
    });
    els.voiceKpiCards.innerHTML = [
      ...latencyCards,
      kpiCard(
        "Est. total cost",
        fmtCost(d.estimated_total_cost_usd),
        `${d.total_evaluations} evaluated turns`,
        "kpi-cost",
      ),
      kpiCard(
        "Avg cost / turn",
        fmtCost(avgCostPerTurn),
        "From evaluation cost metrics",
        "kpi-cost",
      ),
    ].join("");
  }

  els.overviewCards.innerHTML = [
    card("Total Sessions", d.total_sessions, `${d.active_sessions} active`),
    card("Messages", d.total_messages),
    card("Tool Calls", d.total_tool_calls),
    card("Evaluations", d.total_evaluations, `${d.failed_evaluations} failed`),
    card("Avg Eval Score", fmtScore(d.avg_evaluation_score)),
    card("Task Success Rate", fmtPct(outcomes.task_success_rate)),
    card("Escalation Rate", fmtPct(outcomes.escalation_rate)),
    card("Avg Resolution Time", `${Math.round(outcomes.avg_resolution_time_seconds || 0)}s`),
  ].join("");
  renderOutcomeTrend(outcomes.trend || []);
}

function renderOutcomeTrend(trendPoints) {
  if (!els.outcomesTrendChart) return;
  if (!trendPoints.length) {
    els.outcomesTrendChart.innerHTML = "<p>No outcome trend data yet</p>";
    return;
  }

  const points = [...trendPoints].sort((a, b) => a.day.localeCompare(b.day));
  els.outcomesTrendChart.innerHTML = points.map((point) => `
    <div class="trend-row">
      <div class="trend-label">${point.day}</div>
      <div class="trend-values">
        <span class="trend-pill">Sessions: ${point.total_sessions}</span>
        <span class="trend-pill">Success: ${fmtPct(point.task_success_rate)}</span>
        <span class="trend-pill">Escalation: ${fmtPct(point.escalation_rate)}</span>
      </div>
    </div>
  `).join("");
}

async function loadSessions() {
  const sessions = await api("/sessions?limit=20");
  els.sessionsBody.innerHTML = sessions.map((s) => `
    <tr>
      <td><code>${shortId(s.id)}</code></td>
      <td><span class="status-pill ${s.status}">${s.status}</span></td>
      <td>${s.message_count}</td>
      <td>${fmtMs(s.avg_e2e_ms)}</td>
      <td>${fmtScore(s.last_evaluation_score)}</td>
      <td>${fmtDate(s.started_at)}</td>
      <td><button type="button" class="link-btn" data-replay-id="${s.id}">Replay</button></td>
    </tr>
  `).join("") || "<tr><td colspan='7'>No sessions yet</td></tr>";

  els.sessionsBody.querySelectorAll("[data-replay-id]").forEach((btn) => {
    btn.addEventListener("click", () => openReplay(btn.dataset.replayId));
  });
}

function showSection(section) {
  const hubId = SECTION_TO_HUB[section] || "talk";
  const hub = HUBS[hubId];

  document.querySelectorAll(".nav-link[data-hub]").forEach((link) => {
    link.classList.toggle("active", link.dataset.hub === hubId);
  });
  document.querySelectorAll(".hub-tabs").forEach((tabs) => {
    tabs.classList.toggle("hidden", tabs.dataset.hub !== hubId);
  });
  document.querySelectorAll(".hub-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.section === section);
  });

  document.querySelectorAll(".section").forEach((node) => node.classList.add("hidden"));
  const target = document.getElementById(section);
  if (target) target.classList.remove("hidden");

  const sectionLabel = hub?.sections[section] || section;
  els.pageTitle.textContent = hub ? `${hub.label} · ${sectionLabel}` : sectionLabel;
}

function showHub(hubId) {
  const hub = HUBS[hubId];
  if (!hub) return;
  showSection(hub.defaultSection);
}

async function loadSectionData(section) {
  if (!isAuthenticated()) return;
  clearError();
  if (section === "policies") {
    await loadPolicies();
  }
  if (section === "sso") {
    await loadSso();
  }
  if (section === "onboarding") {
    await initWizard({ resetStep: true });
    await loadOnboardingStatus();
  }
  if (section === "knowledge") {
    await loadKnowledge();
    scheduleKnowledgePolling();
  }
  if (section === "handoffs") {
    await loadHandoffs();
  }
  if (section === "api-keys") {
    await loadApiKeys();
  }
}

async function openReplay(sessionId) {
  if (!sessionId) return;
  els.replaySessionInput.value = sessionId;
  showSection("replay");
  await loadReplay(sessionId);
}

async function loadReplay(sessionId) {
  const id = (sessionId || els.replaySessionInput.value || "").trim();
  if (!id) {
    throw new Error("Enter a session UUID to load replay");
  }
  const url = new URL(`/api/v1/sessions/${id}/replay`, window.location.origin);
  if (replayTokenFromHash) {
    url.searchParams.set("replay_token", replayTokenFromHash);
  }
  const res = await fetch(url.toString(), {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(parseApiError(res.status, msg));
  }
  const replay = await res.json();
  renderReplay(replay);
}

function renderReplay(replay) {
  if (!els.replayOutcome || !els.replayTimeline) return;

  if (replay.outcome) {
    els.replayOutcome.textContent = [
      `Session ${shortId(replay.session_id)} (${replay.status})`,
      `intent=${replay.outcome.intent}`,
      `success=${replay.outcome.task_success}`,
      `escalation=${replay.outcome.escalation}`,
      `resolution=${Math.round(replay.outcome.resolution_time_seconds)}s`,
    ].join(" · ");
  } else {
    els.replayOutcome.textContent = `Session ${shortId(replay.session_id)} (${replay.status}) · no outcome recorded`;
  }

  const explanations = replay.explanations || [];
  if (els.replayExplanations) {
    els.replayExplanations.innerHTML = explanations.length
      ? explanations.map((item) => `
          <div class="explain-item ${escapeHtml(item.kind)}">
            <div class="explain-kind">${escapeHtml(item.kind)}</div>
            <div class="explain-decision">${escapeHtml(item.decision)}</div>
            <div class="explain-reason">${escapeHtml(item.reason)}</div>
          </div>
        `).join("")
      : `<div class="card-sub">No explainability signals for this session.</div>`;
  }

  const events = replay.events || [];
  els.replayTimeline.innerHTML = events.map((event) => {
    const role = event.role ? ` · ${event.role}` : "";
    const status = event.status ? ` · ${event.status}` : "";
    return `
      <li class="replay-event ${event.event_type}">
        <div class="replay-event-header">
          <span class="replay-event-type">${event.event_type}</span>
          <span class="replay-event-meta">${fmtDate(event.timestamp)}${role}${status}</span>
        </div>
        <div class="replay-event-summary">${escapeHtml(event.summary || "")}</div>
      </li>
    `;
  }).join("") || "<li class='card-sub'>No timeline events for this session.</li>";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function loadLatency() {
  const buckets = await api("/latency");
  const max = Math.max(...buckets.map((b) => b.avg_ms), 1);
  els.latencyChart.innerHTML = buckets.map((b) => {
    const pct = Math.max(8, (b.avg_ms / max) * 100);
    return `<div class="bar-row">
      <div class="bar-label">${b.metric_name.replace(/_/g, " ")}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%">${Math.round(b.avg_ms)} ms</div></div>
    </div>`;
  }).join("") || "<p>No latency data yet</p>";
}

async function loadEvaluations() {
  const e = await api("/evaluations");
  els.evalSummary.innerHTML = [
    { label: "Total Runs", value: e.total_runs },
    { label: "Avg Score", value: fmtScore(e.avg_score) },
    { label: "Passed", value: e.passed },
    { label: "Warning", value: e.warning },
    { label: "Failed", value: e.failed },
  ].map((s) => `<div class="eval-stat"><div class="value">${s.value}</div><div class="label">${s.label}</div></div>`).join("");

  const metrics = Object.entries(e.by_metric || {});
  els.evalMetrics.innerHTML = metrics.map(([name, score]) => {
    const pct = Math.round(score * 100);
    return `<div class="bar-row">
      <div class="bar-label">${name.replace(/_/g, " ")}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%">${score.toFixed(2)}</div></div>
    </div>`;
  }).join("") || "<p>No evaluation metrics yet</p>";
}

async function loadActivity() {
  const items = await api("/activity?limit=30");
  els.activityList.innerHTML = items.map((i) => `
    <li>
      <span><span class="activity-type">${i.type}</span>${i.summary}</span>
      <span class="activity-time">${fmtDate(i.timestamp)}</span>
    </li>
  `).join("") || "<li>No recent activity</li>";
}

async function loadAlerts() {
  const summary = await api(`/alerts?days=${trendDays}`);
  if (els.alertsSummary) {
    els.alertsSummary.innerHTML = [
      { label: "Active", value: summary.active_count },
      { label: "Critical", value: summary.critical_count },
      { label: "Warning", value: summary.warning_count },
    ].map((item) => `
      <div class="eval-stat">
        <div class="value">${item.value}</div>
        <div class="label">${item.label}</div>
      </div>
    `).join("");
  }
  if (els.alertsList) {
    const alerts = summary.alerts || [];
    els.alertsList.innerHTML = alerts.length
      ? alerts.map((alert) => `
          <li class="alert-item ${escapeHtml(alert.severity)}">
            <div class="alert-header">
              <span class="alert-severity">${escapeHtml(alert.severity)}</span>
              <span class="alert-code">${escapeHtml(alert.code)}</span>
            </div>
            <div class="alert-message">${escapeHtml(alert.message)}</div>
            <div class="alert-meta">
              ${escapeHtml(alert.metric)}: ${alert.observed} vs ${alert.threshold}
            </div>
          </li>
        `).join("")
      : "<li class='card-sub'>No active regression alerts.</li>";
  }
}

function renderPolicyThresholds(thresholds) {
  const entries = Object.entries(thresholds || {});
  if (!entries.length) return "No eval thresholds";
  return entries.map(([key, value]) => `${key}: ${value}`).join(" · ");
}

function renderPolicyPresets(presets) {
  if (!els.policyPresets) return;
  els.policyPresets.innerHTML = presets.map((preset) => `
    <article class="preset-card">
      <div>
        <span class="preset-source">${escapeHtml(preset.source)}</span>
        <h3>${escapeHtml(preset.name)}</h3>
      </div>
      <p class="preset-description">${escapeHtml(preset.description)}</p>
      <div class="preset-thresholds">orchestrator=${escapeHtml(preset.orchestrator_config?.mode || "single")} · ${escapeHtml(renderPolicyThresholds(preset.eval_thresholds))}</div>
      <button type="button" class="link-btn" data-apply-preset="${escapeHtml(preset.slug)}">Apply Preset</button>
    </article>
  `).join("") || "<p class='card-sub'>No policy presets available.</p>";

  els.policyPresets.querySelectorAll("[data-apply-preset]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        clearError();
        await agentConfigApi(`/presets/${btn.dataset.applyPreset}/apply`, {
          method: "POST",
          body: JSON.stringify({ change_note: "Applied from dashboard" }),
        });
        await loadPolicies();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

function renderPolicyVersions(versions) {
  if (!els.policyVersionsBody) return;
  els.policyVersionsBody.innerHTML = versions.map((version) => `
    <tr>
      <td>v${version.version}</td>
      <td><code>${escapeHtml(version.label)}</code></td>
      <td><span class="status-pill ${version.is_active ? "active" : "ended"}">${version.is_active ? "active" : "inactive"}</span></td>
      <td>${escapeHtml(version.change_note || "—")}</td>
      <td>${fmtDate(version.created_at)}</td>
      <td>
        ${version.is_active ? "" : `<button type="button" class="link-btn" data-rollback-version="${version.version}">Rollback</button>`}
      </td>
    </tr>
  `).join("") || "<tr><td colspan='6'>No config versions yet</td></tr>";

  els.policyVersionsBody.querySelectorAll("[data-rollback-version]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        clearError();
        await agentConfigApi("/rollback", {
          method: "POST",
          body: JSON.stringify({
            target_version: Number(btn.dataset.rollbackVersion),
            change_note: "Rollback from dashboard",
          }),
        });
        await loadPolicies();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

async function loadPolicies() {
  const [presets, active, versions] = await Promise.all([
    agentConfigApi("/presets"),
    agentConfigApi("/active"),
    agentConfigApi(""),
  ]);

  if (els.policyActive) {
    if (active) {
      const mode = active.orchestrator_config?.mode || "single";
      els.policyActive.textContent = [
        `Active v${active.version}`,
        active.label,
        `orchestrator=${mode}`,
        active.change_note || "No change note",
      ].join(" · ");
    } else {
      els.policyActive.textContent = "No active agent config yet. Apply a preset to create one.";
    }
  }

  renderPolicyPresets(presets);
  renderPolicyVersions(versions);
}

function parseRoleMappingRules(raw) {
  const value = (raw || "").trim();
  if (!value) return {};
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Role mapping rules must be a JSON object");
  }
  return parsed;
}

function renderSsoConnections(connections) {
  if (!els.ssoConnectionsBody) return;
  els.ssoConnectionsBody.innerHTML = connections.map((connection) => `
    <tr>
      <td>${escapeHtml(connection.provider_type)}</td>
      <td><span class="status-pill ${connection.status}">${escapeHtml(connection.status)}</span></td>
      <td><code>${escapeHtml(shortId(connection.idp_entity_id))}</code></td>
      <td><code>${escapeHtml(connection.sp_entity_id)}</code></td>
      <td>${fmtDate(connection.updated_at)}</td>
      <td>
        <div class="sso-actions">
          ${connection.status !== "active"
            ? `<button type="button" class="link-btn" data-sso-activate="${connection.id}">Activate</button>`
            : `<button type="button" class="link-btn" data-sso-disable="${connection.id}">Disable</button>`}
          <button type="button" class="link-btn" data-sso-metadata="${connection.id}">Metadata</button>
          <button type="button" class="link-btn" data-sso-login="${connection.id}">Test Login</button>
          <button type="button" class="link-btn" data-sso-delete="${connection.id}">Delete</button>
        </div>
      </td>
    </tr>
  `).join("") || "<tr><td colspan='6'>No SAML connections configured yet.</td></tr>";

  const byId = Object.fromEntries(connections.map((item) => [item.id, item]));

  els.ssoConnectionsBody.querySelectorAll("[data-sso-activate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const connection = byId[btn.dataset.ssoActivate];
      await updateSsoConnection(connection.id, {
        status: "active",
        role_mapping_rules: connection.role_mapping_rules || {},
      });
    });
  });

  els.ssoConnectionsBody.querySelectorAll("[data-sso-disable]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const connection = byId[btn.dataset.ssoDisable];
      await updateSsoConnection(connection.id, {
        status: "disabled",
        role_mapping_rules: connection.role_mapping_rules || {},
      });
    });
  });

  els.ssoConnectionsBody.querySelectorAll("[data-sso-metadata]").forEach((btn) => {
    btn.addEventListener("click", () => downloadSsoMetadata(btn.dataset.ssoMetadata));
  });

  els.ssoConnectionsBody.querySelectorAll("[data-sso-login]").forEach((btn) => {
    btn.addEventListener("click", () => testSsoLogin(btn.dataset.ssoLogin));
  });

  els.ssoConnectionsBody.querySelectorAll("[data-sso-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm("Delete this SAML connection?")) return;
      try {
        clearError();
        await ssoApi(`/${btn.dataset.ssoDelete}`, { method: "DELETE" });
        await loadSso();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

async function updateSsoConnection(connectionId, body) {
  try {
    clearError();
    await ssoApi(`/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    await loadSso();
  } catch (err) {
    showError(err.message);
  }
}

async function downloadSsoMetadata(connectionId) {
  try {
    clearError();
    const xml = await ssoApi(`/${connectionId}/metadata`);
    const blob = new Blob([xml], { type: "application/samlmetadata+xml" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `sp-metadata-${connectionId}.xml`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err.message);
  }
}

async function testSsoLogin(connectionId) {
  try {
    clearError();
    const login = await ssoApi(`/${connectionId}/login`);
    if (els.ssoLoginPreview) {
      els.ssoLoginPreview.textContent = JSON.stringify(login, null, 2);
    }
    window.open(login.redirect_url, "_blank", "noopener,noreferrer");
  } catch (err) {
    showError(err.message);
  }
}

function prefillSsoFormDefaults(id) {
  if (els.ssoAcsUrl && !els.ssoAcsUrl.value) {
    els.ssoAcsUrl.value = defaultAcsUrl(id);
  }
  if (els.ssoSpEntityId && !els.ssoSpEntityId.value) {
    els.ssoSpEntityId.value = "voxforge-sp";
  }
}

async function loadSso() {
  const id = await ensureOrgId();
  if (els.ssoOrg) {
    els.ssoOrg.textContent = `Organization ${id}`;
  }
  prefillSsoFormDefaults(id);
  const connections = await ssoApi("");
  renderSsoConnections(connections);
}

function saveKbRecentUploads() {
  // Catalog is server-backed; no localStorage persistence.
}

async function syncKnowledgeDocumentsFromServer() {
  const documents = await knowledgeApi("/documents");
  kbRecentUploads = (documents || []).map((doc) => ({
    document_id: doc.id,
    title: doc.title,
    status: doc.status,
    progress_pct: doc.status === "ready" ? 100 : doc.status === "failed" ? 0 : 50,
    stage: doc.status,
    updated_at: doc.updated_at,
    uploaded_at: doc.created_at,
  }));
  renderKnowledgeUploads();
}

async function knowledgeApi(path, options = {}) {
  const res = await fetch(`/api/v1/knowledge${path}`, {
    credentials: "include",
    ...options,
    headers: authHeaders({ ...(options.headers || {}) }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  if (res.status === 204) return null;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

async function handoffsApi(path, options = {}) {
  const res = await fetch(`/api/v1/handoffs${path}`, {
    credentials: "include",
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }
  if (res.status === 204) return null;
  return res.json();
}

function renderKnowledgeCollections(collections) {
  if (!els.knowledgeCollectionsBody || !els.knowledgeUploadCollection) return;

  els.knowledgeCollectionsBody.innerHTML = collections.map((collection) => `
    <tr>
      <td>${escapeHtml(collection.name)}</td>
      <td>${collection.embedding_dimensions}</td>
      <td>${fmtDate(collection.created_at)}</td>
      <td class="actions-cell">
        <button type="button" class="link-btn" data-kb-collection="${collection.id}">Use</button>
        <button type="button" class="link-btn danger" data-kb-delete-collection="${collection.id}">Delete</button>
      </td>
    </tr>
  `).join("") || "<tr><td colspan='4'>No collections yet</td></tr>";

  els.knowledgeUploadCollection.innerHTML = collections.map((collection) => `
    <option value="${collection.id}">${escapeHtml(collection.name)}</option>
  `).join("") || "<option value=''>Create a collection first</option>";

  els.knowledgeCollectionsBody.querySelectorAll("[data-kb-collection]").forEach((btn) => {
    btn.addEventListener("click", () => {
      els.knowledgeUploadCollection.value = btn.dataset.kbCollection;
      showSection("knowledge");
    });
  });

  els.knowledgeCollectionsBody.querySelectorAll("[data-kb-delete-collection]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const collectionId = btn.dataset.kbDeleteCollection;
      if (!collectionId || !window.confirm("Delete this collection and all documents in it?")) return;
      try {
        clearError();
        await knowledgeApi(`/collections/${collectionId}`, { method: "DELETE" });
        await loadKnowledge();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

function renderKnowledgeUploads() {
  if (!els.knowledgeUploadsBody) return;
  els.knowledgeUploadsBody.innerHTML = kbRecentUploads.map((item) => `
    <tr>
      <td><code>${shortId(item.document_id)}</code>${item.title ? ` · ${escapeHtml(item.title)}` : ""}</td>
      <td><span class="status-pill ${item.status || "queued"}">${escapeHtml(item.status || "queued")}</span></td>
      <td>${item.progress_pct ?? 0}%</td>
      <td>${escapeHtml(item.stage || "—")}</td>
      <td>${fmtDate(item.updated_at || item.uploaded_at)}</td>
      <td><button type="button" class="link-btn danger" data-kb-delete-document="${item.document_id}">Delete</button></td>
    </tr>
  `).join("") || "<tr><td colspan='6'>No documents yet</td></tr>";

  els.knowledgeUploadsBody.querySelectorAll("[data-kb-delete-document]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const documentId = btn.dataset.kbDeleteDocument;
      if (!documentId || !window.confirm("Delete this document?")) return;
      try {
        clearError();
        await knowledgeApi(`/documents/${documentId}`, { method: "DELETE" });
        await syncKnowledgeDocumentsFromServer();
      } catch (err) {
        showError(err.message);
      }
    });
  });
}

async function refreshKnowledgeUploadStatuses() {
  if (!kbRecentUploads.length) {
    renderKnowledgeUploads();
    return;
  }

  const updated = await Promise.all(kbRecentUploads.map(async (item) => {
    try {
      const [document, jobs] = await Promise.all([
        knowledgeApi(`/documents/${item.document_id}`),
        knowledgeApi(`/documents/${item.document_id}/jobs`),
      ]);
      const latestJob = (jobs || [])[0];
      return {
        ...item,
        title: document.title || item.title,
        status: latestJob?.status || document.status,
        progress_pct: latestJob?.progress_pct ?? item.progress_pct ?? 0,
        stage: latestJob?.stage || item.stage || null,
        updated_at: new Date().toISOString(),
        error_message: latestJob?.error_message || null,
      };
    } catch {
      return item;
    }
  }));

  kbRecentUploads = updated;
  saveKbRecentUploads();
  renderKnowledgeUploads();
}

async function loadKnowledge() {
  await ensureOrgId();
  if (els.knowledgeStatus) {
    els.knowledgeStatus.textContent = `Organization ${orgId}`;
  }
  const collections = await knowledgeApi("/collections");
  renderKnowledgeCollections(collections);
  await syncKnowledgeDocumentsFromServer();
  await refreshKnowledgeUploadStatuses();
}

function scheduleKnowledgePolling() {
  if (kbPollTimer) clearInterval(kbPollTimer);
  kbPollTimer = setInterval(() => {
    if (!isAuthenticated() || !kbRecentUploads.length) return;
    refreshKnowledgeUploadStatuses().catch(() => {});
  }, 5000);
}

function renderKnowledgeSearchResults(results) {
  if (!els.knowledgeSearchResults) return;
  els.knowledgeSearchResults.innerHTML = (results || []).map((result) => `
    <li>
      <div><strong>${escapeHtml(result.citation.citation_label)}</strong> · ${result.similarity.toFixed(2)}</div>
      <div class="card-sub">${escapeHtml(result.citation.excerpt)}</div>
    </li>
  `).join("") || "<li class='card-sub'>No matching chunks found.</li>";
}

async function loadHandoffs() {
  const handoffs = await handoffsApi("");
  if (!els.handoffsBody) return;

  els.handoffsBody.innerHTML = handoffs.map((handoff) => `
    <tr>
      <td><code>${shortId(handoff.id)}</code></td>
      <td><code>${shortId(handoff.session_id)}</code></td>
      <td><span class="status-pill ${handoff.status}">${escapeHtml(handoff.status)}</span></td>
      <td>${escapeHtml(handoff.trigger)}</td>
      <td>${escapeHtml(handoff.ticket_id || "—")}</td>
      <td>${escapeHtml(handoff.assigned_to_email || "—")}</td>
      <td>
        <button type="button" class="link-btn" data-handoff-view="${handoff.id}">Context</button>
        ${handoff.status === "pending" ? `<button type="button" class="link-btn" data-handoff-accept="${handoff.id}">Accept</button>` : ""}
      </td>
    </tr>
  `).join("") || "<tr><td colspan='7'>No handoffs yet</td></tr>";

  els.handoffsBody.querySelectorAll("[data-handoff-view]").forEach((btn) => {
    btn.addEventListener("click", () => loadHandoffContext(btn.dataset.handoffView));
  });
  els.handoffsBody.querySelectorAll("[data-handoff-accept]").forEach((btn) => {
    btn.addEventListener("click", () => acceptHandoff(btn.dataset.handoffAccept));
  });
}

async function loadHandoffContext(handoffId) {
  const context = await handoffsApi(`/${handoffId}/context`);
  if (els.handoffContextSummary) {
    els.handoffContextSummary.textContent = [
      `Handoff ${shortId(context.handoff_id)}`,
      `session=${shortId(context.session_id)}`,
      `status=${context.status}`,
    ].join(" · ");
  }
  if (els.handoffContextJson) {
    els.handoffContextJson.textContent = JSON.stringify(context, null, 2);
  }
}

async function acceptHandoff(handoffId) {
  await handoffsApi(`/${handoffId}/accept`, { method: "POST" });
  await loadHandoffs();
}

function renderOnboardingStatus(run) {
  if (!run) {
    els.onboardingStatus.textContent = "No onboarding run yet.";
    els.onboardingJson.textContent = "";
    return;
  }
  els.onboardingStatus.textContent = `Status: ${run.status}`;
  els.onboardingJson.textContent = JSON.stringify(run, null, 2);
}

async function callOnboarding(path, body) {
  const res = await fetch(`/api/v1/onboarding${path}`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(parseApiError(res.status, msg));
  }
  return res.json();
}

async function loadOnboardingStatus() {
  const res = await fetch("/api/v1/onboarding/status", {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(parseApiError(res.status, msg));
  }
  const run = await res.json();
  renderOnboardingStatus(run);
}

async function refreshAll() {
  clearError();
  try {
    await ensureOrgId();
    await Promise.all([
      loadOverview(),
      loadSessions(),
      loadLatency(),
      loadEvaluations(),
      loadActivity(),
      loadAlerts(),
      loadPolicies(),
    ]);
    setConnected(true);
    await maybeOpenWizardAfterLogin();
  } catch (err) {
    setConnected(false);
    showError(err.message);
  }
}

els.loginBtn?.addEventListener("click", () => {
  loginWithPassword().catch((err) => {
    setConnected(false);
    showError(err.message);
  });
});

els.logoutBtn?.addEventListener("click", logout);

els.registerToggleBtn?.addEventListener("click", () => {
  els.registerPanel?.classList.toggle("hidden");
});

els.registerCancelBtn?.addEventListener("click", () => {
  els.registerPanel?.classList.add("hidden");
});

els.registerForm?.addEventListener("submit", (event) => {
  registerAccount(event).catch((err) => showError(err.message));
});

els.wizardInviteForm?.addEventListener("submit", (event) => {
  acceptInvite(event).catch((err) => showError(err.message));
});

els.apiKeyCreateForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    clearError();
    const name = els.apiKeyName?.value.trim();
    if (!name) throw new Error("Enter a key name");
    const created = await apiKeysApi("", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (els.apiKeyCreatedSecret) {
      els.apiKeyCreatedSecret.textContent = `Copy now — shown once:\n${created.raw_key}`;
      els.apiKeyCreatedSecret.classList.remove("hidden");
    }
    els.apiKeyCreateForm?.reset();
    await loadApiKeys();
  } catch (err) {
    showError(err.message);
  }
});

els.connectBtn.addEventListener("click", () => {
  token = els.tokenInput.value.trim();
  orgId = null;
  localStorage.setItem("voxforge_token", token);
  refreshAll();
});

document.querySelectorAll(".toggle-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    setTrendDays(Number(btn.dataset.days));
    if (!isAuthenticated()) return;
    try {
      clearError();
      await loadOverview();
    } catch (err) {
      showError(err.message);
    }
  });
});

els.wizardNextBtn?.addEventListener("click", () => {
  wizardStepForward().catch((err) => showError(err.message));
});

els.wizardBackBtn?.addEventListener("click", () => wizardStepBack());

els.wizardDismissBtn?.addEventListener("click", () => {
  dismissWizard();
  showSection("overview");
});

els.wizardOpenReplayBtn?.addEventListener("click", () => {
  if (wizardState.testSessionId) {
    openReplay(wizardState.testSessionId).catch((err) => showError(err.message));
  }
});

els.wizardOpenOverviewBtn?.addEventListener("click", () => {
  dismissWizard();
  showSection("overview");
  refreshAll().catch((err) => showError(err.message));
});

els.knowledgeRefreshBtn?.addEventListener("click", async () => {
  try {
    clearError();
    await loadKnowledge();
  } catch (err) {
    showError(err.message);
  }
});

els.knowledgeCollectionForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    clearError();
    const name = els.knowledgeCollectionName?.value.trim();
    if (!name) return;
    await knowledgeApi("/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    els.knowledgeCollectionForm.reset();
    await loadKnowledge();
  } catch (err) {
    showError(err.message);
  }
});

els.knowledgeUploadForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    clearError();
    const collectionId = els.knowledgeUploadCollection?.value;
    const file = els.knowledgeUploadFile?.files?.[0];
    if (!collectionId || !file) {
      throw new Error("Select a collection and file to upload");
    }
    const formData = new FormData();
    formData.append("file", file);
    const title = els.knowledgeUploadTitle?.value.trim();
    if (title) formData.append("title", title);

    if (els.knowledgeUploadStatus) {
      els.knowledgeUploadStatus.textContent = `Uploading ${file.name}...`;
    }

    const result = await knowledgeApi(`/collections/${collectionId}/documents`, {
      method: "POST",
      body: formData,
    });

    await syncKnowledgeDocumentsFromServer();
    scheduleKnowledgePolling();
    await refreshKnowledgeUploadStatuses();

    if (els.knowledgeUploadStatus) {
      els.knowledgeUploadStatus.textContent = `Upload queued · document ${shortId(result.document_id)} · job ${shortId(result.job_id)}`;
    }
    els.knowledgeUploadForm.reset();
  } catch (err) {
    if (els.knowledgeUploadStatus) {
      els.knowledgeUploadStatus.textContent = "Upload failed.";
    }
    showError(err.message);
  }
});

els.knowledgeSearchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    clearError();
    const query = els.knowledgeSearchQuery?.value.trim();
    if (!query) return;
    const response = await knowledgeApi("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, limit: 5 }),
    });
    renderKnowledgeSearchResults(response.results || []);
  } catch (err) {
    showError(err.message);
  }
});

els.handoffsRefreshBtn?.addEventListener("click", async () => {
  try {
    clearError();
    await loadHandoffs();
  } catch (err) {
    showError(err.message);
  }
});

els.replayLoadBtn?.addEventListener("click", async () => {
  try {
    clearError();
    await loadReplay();
  } catch (err) {
    showError(err.message);
  }
});

els.ssoCreateForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    clearError();
    const roleMappingRules = parseRoleMappingRules(els.ssoRoleMapping?.value);
    await ssoApi("", {
      method: "POST",
      body: JSON.stringify({
        provider_type: els.ssoProviderType?.value || "generic",
        idp_entity_id: els.ssoIdpEntityId?.value.trim(),
        idp_sso_url: els.ssoIdpSsoUrl?.value.trim(),
        idp_x509_cert: els.ssoIdpCert?.value.trim(),
        sp_entity_id: els.ssoSpEntityId?.value.trim(),
        acs_url: els.ssoAcsUrl?.value.trim(),
        default_role: els.ssoDefaultRole?.value || "member",
        role_mapping_rules: roleMappingRules,
      }),
    });
    els.ssoCreateForm.reset();
    prefillSsoFormDefaults(await ensureOrgId());
    await loadSso();
  } catch (err) {
    showError(err.message);
  }
});

document.querySelectorAll(".nav-link[data-hub]").forEach((link) => {
  link.addEventListener("click", async (e) => {
    e.preventDefault();
    const hubId = link.dataset.hub;
    showHub(hubId);
    try {
      await loadSectionData(HUBS[hubId].defaultSection);
    } catch (err) {
      showError(err.message);
    }
  });
});

document.querySelectorAll(".hub-tab").forEach((tab) => {
  tab.addEventListener("click", async (e) => {
    e.preventDefault();
    const section = tab.dataset.section;
    showSection(section);
    try {
      await loadSectionData(section);
    } catch (err) {
      showError(err.message);
    }
  });
});

setTrendDays(trendDays);

if (token || hasCookieSession()) {
  refreshAll();
  loadOnboardingStatus().catch(() => {});
  scheduleKnowledgePolling();
} else {
  loadWizardStateFromStorage();
  renderWizardAuthStatus();
}

// Deep-link: /dashboard?invite=TOKEN opens wizard at connect step
const inviteToken = new URLSearchParams(window.location.search).get("invite");
if (inviteToken) {
  showSection("onboarding");
  setWizardStep(1);
  els.wizardInviteForm?.classList.remove("hidden");
  if (els.wizardInviteToken) els.wizardInviteToken.value = inviteToken;
  if (els.wizardAuthStatus) {
    els.wizardAuthStatus.textContent = "Accept your invite below, then continue.";
  }
}

function parseDashboardDeepLinks() {
  const hash = window.location.hash.replace(/^#/, "").trim();
  if (!hash) return;
  const params = new URLSearchParams(hash);
  const replaySession = params.get("replay");
  const sessionParam = params.get("session");
  const targetSession = replaySession || sessionParam;
  if (!targetSession) return;

  if (params.get("token")) {
    replayTokenFromHash = params.get("token");
  }
  openReplay(targetSession).catch((err) => showError(err.message));
}

parseDashboardDeepLinks();

setInterval(() => { if (isAuthenticated()) refreshAll(); }, 30000);
