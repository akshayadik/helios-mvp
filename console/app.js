// HELIOS approval console (S4.2, design s4_2_console_design.md).
// Gated by HELIOS_ENABLE_CONSOLE (helios/api/__init__.py).
//
// Review mode (a key with an assigned queue, such as an RQ4 participant): one
// case at a time. The case is fetched and rendered hidden, the view token is
// requested, and only then is the case revealed (K-d). Operations mode (any
// other key): incidents, runs, verdicts with the full chain of evidence, and
// the decision history. Every string is inserted as text, never as HTML (K-h).

import { ApiError, keyStore, makeApi } from "./api.js";
import {
  actionForKey,
  caseModel,
  decisionBody,
  NONE_OF_THESE,
  queueTitle,
} from "./model.js";
import { createCaseTimer } from "./timing.js";

const PAGE = 50;
const $ = (id) => document.getElementById(id);
const keys = keyStore(window.sessionStorage);
const api = makeApi(window.fetch.bind(window), keys.get);

const state = {
  mode: null,
  queue: null,
  offset: 0,
  current: null, // { runId, position, token, timer, model, canDecide }
  busy: false,
};

// ── small DOM helpers (text only) ────────────────────────────────────────────

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("data-")) node.setAttribute(k, v);
    else node[k] = v;
  }
  for (const child of children) {
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function show(id, visible = true) {
  $(id).hidden = !visible;
}

function status(text) {
  $("status").textContent = text ?? "";
  show("status", Boolean(text));
}

function pageHidden() {
  return document.hidden || !document.hasFocus();
}

function describeError(err) {
  if (err instanceof ApiError) return `${err.message} (HTTP ${err.status})`;
  return String(err);
}

// ── sign-in and mode ─────────────────────────────────────────────────────────

async function start() {
  show("login", false);
  show("signout");
  status("Loading…");
  try {
    const queue = await api.get("/v1/queue").catch((err) => {
      if (err instanceof ApiError && (err.status === 403 || err.status === 404)) return null;
      throw err;
    });
    if (queue && queue.items.length) {
      state.mode = "review";
      state.queue = queue;
      await nextCase();
    } else {
      state.mode = "ops";
      await loadIncidents(0);
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      keys.clear();
      signIn("That key was not accepted.");
      return;
    }
    status(describeError(err));
  }
}

function signIn(message) {
  for (const id of ["ops", "case", "signout"]) show(id, false);
  $("where").textContent = "";
  status(message);
  show("login");
  $("key").focus();
}

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const key = $("key").value.trim();
  $("key").value = "";
  if (!key) return;
  keys.set(key);
  start();
});

$("signout").addEventListener("click", () => {
  keys.clear();
  state.current = null;
  signIn("Signed out.");
});

// ── review mode ──────────────────────────────────────────────────────────────

async function nextCase() {
  const queue = await api.get("/v1/queue");
  state.queue = queue;
  const total = queue.items.length;
  if (queue.next_position === null) {
    show("case");
    for (const id of ["decide", "explanation", "coe", "history"]) show(id, false);
    $("case-title").textContent = "All cases are done";
    $("case-state").textContent = "";
    $("where").textContent = queueTitle(total, total);
    $("done").textContent = "Thank you. You can close this window.";
    show("done");
    status("");
    return;
  }
  const item = queue.items[queue.next_position - 1];
  $("where").textContent = queueTitle(item.position, total);
  await openCase(item.run_id, item.position);
}

// ── operations mode ──────────────────────────────────────────────────────────

async function loadIncidents(offset) {
  show("case", false);
  show("ops");
  $("where").textContent = "Operations";
  const page = await api.get(`/v1/incidents?limit=${PAGE}&offset=${offset}`);
  state.offset = offset;
  const rows = $("incident-rows");
  rows.replaceChildren(
    ...page.items.map((i) => {
      const open = el("button", { class: "link", type: "button" }, i.incident_id.slice(0, 12));
      open.addEventListener("click", () => loadIncident(i.incident_id));
      return el(
        "tr",
        {},
        el("td", {}, open),
        el("td", {}, i.runs),
        el("td", {}, i.confirmed),
        el("td", {}, i.needs_review),
      );
    }),
  );
  $("page-label").textContent = `${offset + 1}–${offset + page.items.length} of ${page.total}`;
  $("prev").disabled = offset === 0;
  $("next").disabled = offset + page.items.length >= page.total;
  status("");
}

$("prev").addEventListener("click", () => loadIncidents(Math.max(0, state.offset - PAGE)));
$("next").addEventListener("click", () => loadIncidents(state.offset + PAGE));

async function loadIncident(incidentId) {
  const detail = await api.get(`/v1/incidents/${encodeURIComponent(incidentId)}`);
  $("incident-title").textContent = `Incident ${incidentId.slice(0, 12)}`;
  $("run-rows").replaceChildren(
    ...detail.runs.map((r) => {
      const open = el("button", { class: "link", type: "button" }, "Open");
      open.addEventListener("click", () => {
        show("ops", false);
        openCase(r.run_id, null);
      });
      return el(
        "tr",
        {},
        el("td", {}, r.variant ?? ""),
        el("td", {}, r.state),
        el("td", {}, r.confidence === null ? "n/a" : r.confidence.toFixed(3)),
        el("td", {}, r.top3.join(", ")),
        el("td", {}, open),
      );
    }),
  );
  show("incident");
}

// ── one case ─────────────────────────────────────────────────────────────────

function renderRanked(model) {
  $("case-state").textContent = model.state;
  $("confidence-meter").value = model.confidence ?? 0;
  $("confidence-text").textContent = model.confidenceText;
  $("ranked").replaceChildren(
    ...model.ranked.map((r) =>
      el("li", {}, el("span", { class: "svc" }, r.service), el("span", { class: "score" }, r.score)),
    ),
  );
  const trig = $("trigger");
  trig.replaceChildren();
  if (model.trigger) {
    trig.append(
      el("p", {}, "Triggered ", el("time", { dateTime: model.trigger.time }, model.trigger.time)),
      el("p", { class: "hint" }, `Trigger suspects: ${model.trigger.suspects.join(", ") || "none"}`),
    );
  }
  const act = $("action");
  act.replaceChildren();
  if (model.action) {
    act.append(
      el("p", {}, "Recommendation: ", el("strong", {}, model.action.text)),
      el("p", { class: "hint" }, model.action.validation),
    );
    if (model.action.shadow) {
      act.append(el("p", { class: "hint" }, "Shadow mode: recorded for comparison only."));
    }
  }
  show("action", Boolean(model.action));
  $("degraded").textContent = model.degraded
    ? `HELIOS control plane degraded (${model.degraded}) when this run started.`
    : "";
  show("degraded", Boolean(model.degraded));
}

function renderClaims(model) {
  const list = $("claims");
  list.replaceChildren();
  show("no-narrative", model.narrative === null);
  if (model.narrative === null) return;
  for (const claim of model.narrative.claims) {
    const cites = claim.cites.map((c) => {
      const rows = c.rows.length
        ? el("dl", {}, ...c.rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]))
        : el("p", { class: "hint" }, c.found ? "No details." : "Not found in the chain of evidence.");
      return el("details", { class: "cite" }, el("summary", {}, c.id), rows);
    });
    list.append(el("li", {}, el("p", {}, claim.sentence), el("div", { class: "cites" }, ...cites)));
  }
}

function renderChooser(model) {
  $("choices").replaceChildren(
    ...model.rejectOptions.map((service, i) =>
      el(
        "label",
        { class: "choice" },
        el("input", { type: "radio", name: "chosen", value: service, checked: i === 0 }),
        service === NONE_OF_THESE ? "None of these" : service,
      ),
    ),
    el("label", { class: "choice" }, el("input", { type: "radio", name: "chosen", value: "" }), "Not sure"),
  );
}

async function renderOps(runId) {
  show("coe");
  const coe = await api.get(`/v1/verdicts/${runId}/coe`).catch(() => null);
  $("coe-status").textContent = coe ? coe.verification : "No chain of evidence for this run.";
  $("coe-json").textContent = coe ? JSON.stringify(coe.entry, null, 1) : "";
  const history = await api.get(`/v1/verdicts/${runId}/decisions`);
  $("history-rows").replaceChildren(
    ...history.decisions.map((d) =>
      el(
        "li",
        {},
        `${d.decision}${d.chosen_service ? ` (${d.chosen_service})` : ""} by ${d.key_id}` +
          `${d.simulated ? " [simulated]" : ""}, ${Math.round(d.decision_ms)} ms`,
      ),
    ),
  );
  show("history", history.decisions.length > 0);
}

async function openCase(runId, position) {
  state.busy = true;
  show("case", false);
  show("done", false);
  show("chooser", false);
  status("Loading the case…");
  const verdict = await api.get(`/v1/verdicts/${runId}`);
  const coe = await api.get(`/v1/verdicts/${runId}/coe`).catch(() => null);
  const model = caseModel(verdict, coe ? coe.entry : null);
  $("case-title").textContent =
    position === null
      ? `Run ${runId.slice(0, 12)}${model.variant ? ` · ${model.variant}` : ""}`
      : "Which service caused this incident?";
  renderRanked(model);
  renderClaims(model);
  renderChooser(model);
  show("explanation");
  $("note").value = "";
  if (state.mode === "ops") await renderOps(runId);
  else for (const id of ["coe", "history"]) show(id, false);

  // Reveal only once the view token is issued (K-d).
  let token = null;
  try {
    token = (await api.post(`/v1/verdicts/${runId}/views`)).view_token;
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 403)) throw err;
  }
  const timer = createCaseTimer();
  state.current = { runId, position, token, timer, model, canDecide: token !== null };
  show("decide", token !== null && model.needsReview);
  for (const b of document.querySelectorAll("#decide button")) b.disabled = false;
  status("");
  show("case");
  timer.reveal(performance.now(), pageHidden());
  $("case-title").focus();
  state.busy = false;
}

// ── decisions ────────────────────────────────────────────────────────────────

async function decide(action, chosen) {
  const cur = state.current;
  if (!cur || !cur.canDecide || state.busy || !cur.timer.revealed) return;
  if (action === "reject" && chosen === undefined) {
    show("chooser");
    $("choices").querySelector("input")?.focus();
    return;
  }
  state.busy = true;
  const timing = cur.timer.stop(performance.now());
  for (const b of document.querySelectorAll("#decide button")) b.disabled = true;
  const body = decisionBody(action, cur.token, timing, chosen, $("note").value);
  try {
    await api.post(`/v1/verdicts/${cur.runId}/decisions`, body);
  } catch (err) {
    state.busy = false;
    if (err instanceof ApiError && err.status === 410) {
      status("The case was open too long and has been reopened.");
      await openCase(cur.runId, cur.position);
      return;
    }
    // Nothing was recorded: reopen the case (a new view) and say why.
    await openCase(cur.runId, cur.position);
    status(`Not recorded: ${describeError(err)}`);
    return;
  }
  state.busy = false;
  if (state.mode === "review") {
    await nextCase();
  } else {
    status(`Recorded: ${action}.`);
    await openCase(cur.runId, null);
  }
}

$("decide").addEventListener("click", (event) => {
  const action = event.target.closest("button")?.dataset.action;
  if (action) decide(action);
});

$("confirm-reject").addEventListener("click", () => {
  const picked = document.querySelector('input[name="chosen"]:checked');
  decide("reject", picked && picked.value ? picked.value : null);
});

$("cancel-reject").addEventListener("click", () => show("chooser", false));

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || !$("chooser").hidden) return;
  const action = actionForKey(event.key, event.target.tagName);
  if (action && !$("decide").hidden) {
    event.preventDefault();
    decide(action);
  }
});

const track = () => state.current?.timer.visibility(performance.now(), pageHidden());
document.addEventListener("visibilitychange", track);
window.addEventListener("blur", track);
window.addEventListener("focus", track);

if (keys.get()) start();
else signIn("");
