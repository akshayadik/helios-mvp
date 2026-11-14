// View models for the approval console (S4.2 design K-b, K-c, K-e).
// Gated by HELIOS_ENABLE_CONSOLE (helios/api/__init__.py).
//
// Pure functions from API responses to what the screen shows, so they can be
// tested without a browser. Nothing here builds HTML: the page inserts every
// string as text, because narratives and evidence carry model output and log
// lines (K-h).

export const TOP_N = 5;
export const NONE_OF_THESE = "none";
const PERCENT = 10 ** 2;
const MAX_VALUE_CHARS = 160;

export const KEY_ACTIONS = Object.freeze({
  a: "accept",
  e: "escalate",
  r: "reject",
});

const STATE_LABELS = Object.freeze({
  confirmed: "Confirmed",
  provisional: "Provisional: needs review",
  non_converged: "Not converged: needs review",
});

export function stateLabel(state) {
  return STATE_LABELS[state] ?? state;
}

export function percent(confidence) {
  if (confidence === null || confidence === undefined) return "n/a";
  return `${Math.round(confidence * PERCENT)}%`;
}

export function formatScore(score) {
  return score === null || score === undefined ? "" : score.toFixed(3);
}

// Evidence items a claim may cite (the verifier's rule: step items, without
// worker claims, plus the F step).
export function citableIndex(entry) {
  const index = new Map();
  if (!entry || !Array.isArray(entry.steps)) return index;
  for (const step of entry.steps) {
    for (const item of step.items ?? []) {
      if (typeof item.id === "string" && !item.id.includes(":claim")) {
        index.set(item.id, item);
      }
    }
    if (step.id === "F") index.set("F", step);
  }
  return index;
}

function shortText(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text === undefined) return "";
  return text.length > MAX_VALUE_CHARS ? `${text.slice(0, MAX_VALUE_CHARS)}…` : text;
}

// One cited item as label/value rows for the evidence panel.
export function describeEvidence(item) {
  if (!item) return [];
  return Object.entries(item)
    .filter(([key]) => key !== "id" && key !== "items")
    .map(([key, value]) => [key.replaceAll("_", " "), shortText(value)]);
}

export function caseModel(verdict, coeEntry) {
  const index = citableIndex(coeEntry);
  const ranked = (verdict.ranked ?? []).slice(0, TOP_N).map((r) => ({
    rank: r.rank,
    service: r.service,
    score: formatScore(r.score),
  }));
  const narrative =
    verdict.narrative === null || verdict.narrative === undefined
      ? null
      : {
          claims: verdict.narrative.claims.map((c) => ({
            sentence: c.sentence,
            kind: c.kind,
            cites: c.cites.map((id) => ({
              id,
              found: index.has(id),
              rows: describeEvidence(index.get(id)),
            })),
          })),
        };
  return {
    runId: verdict.run_id,
    variant: verdict.variant ?? null, // null for a blind key
    state: stateLabel(verdict.state),
    needsReview: Boolean(verdict.needs_review),
    confidence: verdict.confidence,
    confidenceText: percent(verdict.confidence),
    ranked,
    top: ranked.length ? ranked[0].service : null,
    trigger: verdict.trigger
      ? {
          time: new Date(verdict.trigger.time_s * 1000).toISOString(),
          suspects: verdict.trigger.suspects,
        }
      : null,
    narrative,
    rejectOptions: [...ranked.slice(1).map((r) => r.service), NONE_OF_THESE],
  };
}

export function queueTitle(position, total) {
  return `Case ${position} of ${total}`;
}

// The action a key press asks for, unless the reviewer is typing a note.
export function actionForKey(key, targetTag) {
  if (targetTag === "TEXTAREA" || targetTag === "INPUT") return null;
  return KEY_ACTIONS[String(key).toLowerCase()] ?? null;
}

// The decision request body (K-d, K-e).
export function decisionBody(decision, token, timing, chosen, note) {
  const body = {
    decision,
    view_token: token,
    client_ms: timing.client_ms,
    client_hidden_ms: timing.client_hidden_ms,
  };
  if (decision === "reject" && chosen) body.chosen_service = chosen;
  if (note && note.trim()) body.note = note.trim();
  return body;
}
