// S4.2 console logic tests (design K-i): node --test tests/console/
// Pure modules only; the page itself is checked in the walk-through (K-j).

import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, keyStore, makeApi } from "../../console/api.js";
import {
  actionForKey,
  actionText,
  caseModel,
  citableIndex,
  decisionBody,
  describeEvidence,
  NONE_OF_THESE,
  percent,
  queueTitle,
  stateLabel,
} from "../../console/model.js";
import { createCaseTimer } from "../../console/timing.js";

// ── timing (K-d) ─────────────────────────────────────────────────────────────

test("client_ms runs from reveal to the click", () => {
  const t = createCaseTimer();
  t.reveal(1000);
  assert.equal(t.revealed, true);
  assert.deepEqual(t.stop(5250.4567), { client_ms: 4250.457, client_hidden_ms: 0 });
  assert.equal(t.revealed, false);
});

test("hidden time adds up across several absences", () => {
  const t = createCaseTimer();
  t.reveal(0);
  t.visibility(2000, true);
  t.visibility(2500, true); // repeated hide events do not restart the clock
  t.visibility(3000, false);
  t.visibility(3000, false);
  t.visibility(7000, true);
  t.visibility(8000, false);
  assert.deepEqual(t.stop(9000), { client_ms: 9000, client_hidden_ms: 2000 });
});

test("a case still hidden at the click counts up to the click", () => {
  const t = createCaseTimer();
  t.reveal(0, true);
  assert.deepEqual(t.stop(400), { client_ms: 400, client_hidden_ms: 400 });
});

test("visibility before reveal or after stop is ignored, and stop needs a reveal", () => {
  const t = createCaseTimer();
  t.visibility(10, true);
  assert.throws(() => t.stop(20), /not revealed/);
  t.reveal(150);
  t.stop(250);
  t.visibility(300, true);
  assert.throws(() => t.stop(400), /not revealed/);
  t.reveal(1000); // a reopened case starts again
  assert.deepEqual(t.stop(1500), { client_ms: 500, client_hidden_ms: 0 });
});

// ── view model (K-b, K-c, K-e) ───────────────────────────────────────────────

const ENTRY = {
  steps: [
    { id: "T", suspects: ["checkout"] },
    {
      id: "P:dpipe",
      items: [
        { id: "D:checkout:error", service: "checkout", value: { after: 12, before: 0 } },
        { id: "L:metric:claim", service: "checkout" },
      ],
    },
    { id: "F", ranked: ["checkout", "email"], confidence: 0.88 },
  ],
};

const VERDICT = {
  run_id: "run-p",
  state: "provisional",
  needs_review: true,
  confidence: 0.876,
  ranked: [
    { rank: 1, service: "checkout", score: 0.9 },
    { rank: 2, service: "email", score: 0.4 },
    { rank: 3, service: "ad", score: null },
    { rank: 4, service: "cart", score: 0.1 },
    { rank: 5, service: "kafka", score: 0.05 },
    { rank: 6, service: "frontend", score: 0.01 },
  ],
  trigger: { time_s: 1700000000, suspects: ["checkout"], source: "detector" },
  narrative: {
    claims: [
      {
        slot: "story",
        kind: "ranking",
        sentence: "checkout errors rose.",
        cites: ["D:checkout:error", "F", "G:missing"],
      },
    ],
  },
};

test("citable index follows the verifier: items without worker claims, plus F", () => {
  const index = citableIndex(ENTRY);
  assert.deepEqual([...index.keys()].sort(), ["D:checkout:error", "F"]);
  assert.equal(citableIndex(null).size, 0);
  assert.equal(citableIndex({}).size, 0);
});

test("evidence rows are label/value text, long values cut", () => {
  const rows = describeEvidence({ id: "x", trigger_time: "t", value: "v".repeat(400) });
  assert.deepEqual(rows[0], ["trigger time", "t"]);
  assert.equal(rows[1][1].length, 161);
  assert.ok(rows[1][1].endsWith("…"));
  assert.deepEqual(describeEvidence(undefined), []);
});

test("case model: top five, confidence, trigger, cited evidence", () => {
  const m = caseModel(VERDICT, ENTRY);
  assert.equal(m.ranked.length, 5);
  assert.equal(m.top, "checkout");
  assert.equal(m.ranked[2].score, "");
  assert.equal(m.confidenceText, "88%");
  assert.equal(m.state, "Provisional: needs review");
  assert.equal(m.trigger.time, "2023-11-14T22:13:20.000Z");
  const [claim] = m.narrative.claims;
  assert.deepEqual(
    claim.cites.map((c) => [c.id, c.found]),
    [
      ["D:checkout:error", true],
      ["F", true],
      ["G:missing", false],
    ],
  );
  assert.deepEqual(claim.cites[0].rows[0], ["service", "checkout"]);
  assert.deepEqual(m.rejectOptions, ["email", "ad", "cart", "kafka", NONE_OF_THESE]);
});

test("variant shown only when the API sends it (null for blind keys)", () => {
  assert.equal(caseModel(VERDICT, ENTRY).variant, null);
  assert.equal(caseModel({ ...VERDICT, variant: "HELIOS-Full" }, ENTRY).variant, "HELIOS-Full");
});

test("the noExpl condition shows no explanation (narrative null)", () => {
  const m = caseModel({ ...VERDICT, narrative: null }, ENTRY);
  assert.equal(m.narrative, null);
  assert.equal(m.ranked.length, 5);
});

test("labels and helpers", () => {
  assert.equal(percent(null), "n/a");
  assert.equal(percent(0.333), "33%");
  assert.equal(stateLabel("non_converged"), "Not converged: needs review");
  assert.equal(stateLabel("other"), "other");
  assert.equal(queueTitle(3, 12), "Case 3 of 12");
  assert.equal(caseModel({ ...VERDICT, trigger: null }, null).trigger, null);
});

test("keyboard shortcuts, except while typing", () => {
  assert.equal(actionForKey("a", "BODY"), "accept");
  assert.equal(actionForKey("E", "BODY"), "escalate");
  assert.equal(actionForKey("r", "BUTTON"), "reject");
  assert.equal(actionForKey("x", "BODY"), null);
  assert.equal(actionForKey("a", "TEXTAREA"), null);
  assert.equal(actionForKey("a", "INPUT"), null);
});

test("decision body carries both client measures; chosen service on reject only", () => {
  const timing = { client_ms: 1200, client_hidden_ms: 30 };
  assert.deepEqual(decisionBody("accept", "tok", timing, "email", "  "), {
    decision: "accept",
    view_token: "tok",
    client_ms: 1200,
    client_hidden_ms: 30,
  });
  const reject = decisionBody("reject", "tok", timing, "email", " looks like email ");
  assert.equal(reject.chosen_service, "email");
  assert.equal(reject.note, "looks like email");
  assert.equal("chosen_service" in decisionBody("reject", "tok", timing, null, ""), false);
});

// ── API client (K-h) ─────────────────────────────────────────────────────────

function fakeFetch(status, body, calls) {
  return async (path, init) => {
    calls.push({ path, init });
    return {
      ok: status < 400,
      status,
      json: async () => {
        if (body === undefined) throw new Error("no body");
        return body;
      },
    };
  };
}

test("requests are relative, keyed by header, never by URL or cookie", async () => {
  const calls = [];
  const api = makeApi(fakeFetch(200, { ok: true }, calls), () => "secret-key");
  assert.deepEqual(await api.post("/v1/verdicts/r/views", { a: 1 }), { ok: true });
  const [{ path, init }] = calls;
  assert.equal(path, "/v1/verdicts/r/views");
  assert.equal(init.method, "POST");
  assert.equal(init.headers["X-API-Key"], "secret-key");
  assert.equal(init.credentials, "omit");
  assert.equal(init.body, '{"a":1}');
  assert.ok(!path.includes("secret-key"));
});

test("problem responses become ApiError with status and title", async () => {
  const api = makeApi(fakeFetch(410, { title: "view token expired" }, []), () => null);
  await assert.rejects(api.get("/v1/x"), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.status, 410);
    assert.equal(err.message, "view token expired");
    return true;
  });
  const bare = makeApi(fakeFetch(502, undefined, []), () => null);
  await assert.rejects(bare.get("/v1/x"), /HTTP 502/);
});

test("the key lives in the session store only", () => {
  const data = new Map();
  const storage = {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
  const keys = keyStore(storage);
  assert.equal(keys.get(), null);
  keys.set("k1");
  assert.equal(keys.get(), "k1");
  keys.clear();
  assert.equal(keys.get(), null);
});

// ── recommendation and control-plane state (S4.5–S4.7) ───────────────────────

test("the proposal shows as a recommendation; none for a blind key", () => {
  const action = { kind: "restart", target: "cart", mode: "recommend", validation: "PASS", reason: "validated" };
  const m = caseModel({ ...VERDICT, action, control_plane_degraded: "helios.model" }, ENTRY);
  assert.deepEqual(m.action, {
    text: "Restart cart",
    validation: "Shadow validation: PASS (validated)",
    shadow: false,
  });
  assert.equal(m.degraded, "helios.model");
  assert.equal(caseModel(VERDICT, ENTRY).action, null);
  assert.equal(caseModel(VERDICT, ENTRY).degraded, null);
  assert.equal(actionText({ ...action, kind: "none", target: null }), null);
  assert.equal(actionText({ ...action, mode: "shadow" }).shadow, true);
  assert.equal(actionText({ ...action, kind: "escalate-to-human" }).text, "Hand to a person: cart");
});
