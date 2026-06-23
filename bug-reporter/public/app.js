// Reporter page logic: load per-mod config, validate the save client-side,
// then the two-phase submit (presign, direct PUT to R2, file the report).

const API_BASE = window.API_BASE || "";

const state = {
  mod: null,
  config: null,
  file: null,
  turnstileToken: null,
  turnstileWidgetId: null,
  submitting: false,
  uploadedSubmissionId: null,
};

const $ = (id) => document.getElementById(id);

async function init() {
  const modId = new URLSearchParams(location.search).get("mod");
  if (!modId) {
    return disableForm("No mod was specified. Open this page from the Report a Bug link on the mod's Workshop page or Discord.");
  }

  let res;
  try {
    res = await fetch(`${API_BASE}/api/config?mod=${encodeURIComponent(modId)}`);
  } catch {
    return disableForm("Could not reach the server. Please try again later.");
  }
  if (res.status === 404) {
    return disableForm("This mod is not set up for bug reports. Use the Report a Bug link from the mod's page.");
  }
  if (!res.ok) {
    return disableForm("Could not load the report form. Please try again later.");
  }

  state.config = await res.json();
  state.mod = state.config.mod;

  $("mod-name").textContent = state.mod.display_name;
  $("max-size").textContent = formatBytes(state.config.max_upload_bytes);
  document.title = `Report a Bug - ${state.mod.display_name}`;
  $("report-form").hidden = false;

  setupFileDrop();
  setupTurnstile();
  $("report-form").addEventListener("submit", onSubmit);
}

function disableForm(message) {
  $("report-form").hidden = true;
  const s = $("status");
  s.textContent = message;
  s.hidden = false;
}

function setupTurnstile() {
  window.__tsOnload = () => {
    state.turnstileWidgetId = window.turnstile.render("#turnstile", {
      sitekey: state.config.turnstile_sitekey,
      callback: (token) => { state.turnstileToken = token; },
      "expired-callback": () => { state.turnstileToken = null; },
      "error-callback": () => { state.turnstileToken = null; },
    });
  };
  const script = document.createElement("script");
  script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=__tsOnload";
  script.async = true;
  script.defer = true;
  document.head.appendChild(script);
}

function resetTurnstile() {
  state.turnstileToken = null;
  if (window.turnstile && state.turnstileWidgetId !== null) {
    window.turnstile.reset(state.turnstileWidgetId);
  }
}

function setupFileDrop() {
  const drop = $("drop-zone");
  const input = $("file-input");
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("dragover");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length) handleFile(input.files[0]);
  });
}

async function handleFile(file) {
  setFileError("");
  state.file = null;
  state.uploadedSubmissionId = null;
  $("file-name").hidden = true;

  if (!file.name.toLowerCase().endsWith(".eu5")) {
    return setFileError("That is not a .eu5 save file.");
  }
  if (file.size > state.config.max_upload_bytes) {
    return setFileError(`That file is too large. The limit is ${formatBytes(state.config.max_upload_bytes)}.`);
  }
  if (!(await hasSavMagic(file))) {
    return setFileError("That file is not a valid EU5 save (it has no SAV header).");
  }

  state.file = file;
  const nameEl = $("file-name");
  nameEl.textContent = `${file.name} - ${formatBytes(file.size)}`;
  nameEl.hidden = false;
}

function hasSavMagic(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const b = new Uint8Array(reader.result);
      resolve(b.length >= 3 && b[0] === 0x53 && b[1] === 0x41 && b[2] === 0x56);
    };
    reader.onerror = () => resolve(false);
    reader.readAsArrayBuffer(file.slice(0, 3));
  });
}

const REQUIRED = {
  title: "Short summary",
  steps: "Steps to reproduce",
  expected: "What you expected",
  actual: "What actually happened",
  eu5_version: "EU5 version",
  mod_version: "Mod version",
  other_mods: "Other mods loaded",
};

function collectFields() {
  const data = new FormData($("report-form"));
  const fields = {};
  for (const [key, value] of data.entries()) fields[key] = String(value).trim();
  return fields;
}

function firstMissing(fields) {
  for (const [key, label] of Object.entries(REQUIRED)) {
    if (!fields[key]) return label;
  }
  return null;
}

async function onSubmit(e) {
  e.preventDefault();
  if (state.submitting) return;
  clearResult();

  const fields = collectFields();
  const missing = firstMissing(fields);
  if (missing) return setResult("error", `Please fill in: ${missing}.`);
  if (!state.file) return setResult("error", "Please attach your .eu5 save file.");
  if (!state.uploadedSubmissionId && !state.turnstileToken) {
    return setResult("error", "Please complete the verification challenge.");
  }

  setSubmitting(true);
  try {
    let submissionId = state.uploadedSubmissionId;
    if (!submissionId) {
      const presign = await postJson(`${API_BASE}/api/presign`, {
        mod: state.mod.id,
        size: state.file.size,
        turnstile_token: state.turnstileToken,
      });
      if (!presign.ok) return failFromApi(presign);
      submissionId = presign.data.submission_id;

      setProgressLabel("Uploading save");
      await uploadFile(presign.data.upload_url, state.file);
      state.uploadedSubmissionId = submissionId;
    }

    setProgressLabel("Filing report");
    const submit = await postJson(`${API_BASE}/api/submit`, {
      submission_id: submissionId,
      fields,
    });
    if (!submit.ok) {
      if (submit.status === 410) state.uploadedSubmissionId = null;
      return failFromApi(submit);
    }

    state.uploadedSubmissionId = null;
    showSuccess(submit.data.issue_url);
  } catch {
    setResult("error", "The upload did not finish. Check your connection and press Submit to try again.");
    resetTurnstile();
  } finally {
    setSubmitting(false);
  }
}

function uploadFile(url, file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("upload error"));
    xhr.ontimeout = () => reject(new Error("upload timeout"));
    showProgress(true);
    setProgress(0);
    xhr.send(file);
  });
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  return { ok: res.ok, status: res.status, data };
}

function failFromApi(result) {
  const known = {
    403: "Verification failed. Please solve the challenge again.",
    404: "This mod is not set up for bug reports.",
    409: "Your upload could not be verified. Please try again.",
    410: "This report timed out. Please start again from the top.",
    413: "That file is too large.",
    415: "That file is not a valid EU5 save.",
    422: "Some required fields are missing.",
    429: "Too many reports from your connection. Please wait a while and try again.",
  };
  let message = known[result.status];
  if (!message && result.status >= 500) {
    message = state.uploadedSubmissionId
      ? "Your save uploaded, but filing the report failed. Press Submit to try again."
      : "The server had a problem. Please try again shortly.";
  }
  setResult("error", message || "Something went wrong. Please try again.");
  if (result.status === 403 || result.status === 429) resetTurnstile();
}

function showSuccess(issueUrl) {
  showProgress(false);
  const r = $("result");
  r.className = "result success";
  r.innerHTML = "";
  const p = document.createElement("p");
  p.textContent = "Thank you. Your report has been filed.";
  r.appendChild(p);
  if (issueUrl) {
    const a = document.createElement("a");
    a.href = issueUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "View your report";
    r.appendChild(a);
  }
  r.hidden = false;
  $("report-form").querySelectorAll("input, textarea, button").forEach((el) => {
    el.disabled = true;
  });
}

function setSubmitting(on) {
  state.submitting = on;
  const btn = $("submit-btn");
  btn.disabled = on;
  btn.textContent = on ? "Working..." : "Submit report";
  if (!on) showProgress(false);
}

function showProgress(on) {
  $("progress-wrap").hidden = !on;
}

function setProgress(frac) {
  const pct = Math.round(frac * 100);
  $("progress-bar").style.width = `${pct}%`;
  $("progress-text").textContent = `${pct}%`;
}

function setProgressLabel(text) {
  showProgress(true);
  $("progress-label").textContent = text;
}

function setFileError(msg) {
  $("file-error").textContent = msg;
}

function clearResult() {
  const r = $("result");
  r.hidden = true;
  r.textContent = "";
  r.className = "result";
}

function setResult(kind, msg) {
  const r = $("result");
  r.className = `result ${kind}`;
  r.textContent = msg;
  r.hidden = false;
}

function formatBytes(bytes) {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

init();
