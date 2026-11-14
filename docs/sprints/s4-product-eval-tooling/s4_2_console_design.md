# S4.2 Approval console (RQ4 instrument): design (draft)

**Row:** S2-M9-ENG02 · **Effort:** 2 days · **Depends on:** S4.1 (API), S2.8 (grounded narratives), S4.3 (compose) · **Feeds:** E4 RQ4 user study (only if IRB approval arrives by 2027-02-05) · **Status:** approved 2026-11-14 (K-a to K-j as recommended)

## 1. What is fixed already

- **Task** (`helios_task_breakdown.md` S4.2):
  - ranked set with confidence;
  - grounded narrative with evidence links, with a toggle for noExpl;
  - accept / escalate / reject with decision timing;
  - a simulated-HITL mode for runs.
- **Done when:** a walk-through, and timing capture verified.
- **E-H7** (exploratory, RQ4): HELIOS-Full vs HELIOS-noExpl on correct interpretation, time to decision and trust. 24 participants in a Latin square (E4). The study needs IRB approval; the instrument is built and verified regardless (S4 plan).
- **From S4.1, already built:**
  - server-side decision timing (a view token, then a decision; `decision_ms` from the server clock);
  - a signed decisions ledger;
  - per-key roles;
  - noExpl comes from the stored run: its `narrative` is null, never a client toggle;
  - label-derived data is never returned.

## 2. What exists today

| Piece | State |
|---|---|
| API | `GET /v1/incidents`, `/v1/incidents/{id}`, `/v1/verdicts/{run_id}` (ranked list, scores, confidence, state, trigger, routing, narrative with claims and `cites`), `/coe`, `POST /views`, `POST /decisions`, `GET /decisions` |
| Evidence links | Every claim's `cites` (for example `D:checkout:error`, `G:checkout:wait_from`, `L:metric:M2`, `F`) names an item in the run's CoE entry (`steps[].items[].id`, plus the F step). The verifier resolves them the same way (`verifier._citable`). The CoE endpoint already returns the entry, so no new evidence endpoint is needed |
| Compose | `deploy/compose.yaml` has a commented `console` slot on the `front` network |
| Front end | None. No Node toolchain is used in the repo (Node exists on the build machine only) |

## 3. Decisions for the owner

### K-a. Front-end technology

- **Recommended: a static, build-free console.**
  - Plain HTML, CSS and ES-module JavaScript under `console/`, with no npm dependencies and no build step;
  - served by an `nginx` container pinned by digest. The same nginx proxies `/v1/*` and `/health` to the `api` service, so the console and the API share one origin: no CORS and no API change for hosting;
  - published on loopback port 8081, like the API (C-f of S4.3).
- **Why:** nothing to supply-chain audit beyond one pinned image, and nothing to rebuild. The UI is a handful of screens, and the timing logic must stay small and inspectable.
- (b) React and Vite: a nicer development loop, but an npm dependency tree and a lock file to pin and audit, plus a build stage in the image.
- (c) Server-rendered pages from FastAPI (Jinja2): no JavaScript build either, but the timing protocol (K-d) needs client-side control of when the case is revealed.

### K-b. Screens

- **Recommended:** two modes in one console.
  - **Review** (the RQ4 screen, also used in operations): one case at a time:
    - state badge (provisional, non-converged);
    - ranked services (top 5) with scores, and the calibrated confidence shown as a percentage with a bar;
    - trigger time and the trigger's suspects;
    - the narrative, with each claim's citations as chips that expand the cited CoE item in place;
    - the decision bar: accept, escalate, reject, with an optional note, plus keyboard shortcuts A, E and R.
  - **Operations** (reader keys): incident list, incident detail, run list, verdict and CoE view, and a decisions history per run.
- **Meaning of the decisions:**
  - accept: the top-ranked service is the root cause;
  - reject: it is not;
  - escalate: hand the case to the next tier without judging.

### K-c. noExpl condition and evidence visibility

- **Recommended:**
  - the condition comes only from the stored run (S4.1 A-b): a noExpl run has no narrative, so the console shows the ranked set, confidence and trigger only. There is no client toggle;
  - evidence is reachable **only through claim citations**. In review mode there is no standalone CoE browser, so a noExpl participant cannot rebuild the explanation from raw evidence, and the two conditions differ only by the narrative;
  - the operations mode keeps the full CoE view.
- (b) Show the CoE browser in both conditions. More information for participants, but it blurs the E-H7 contrast.

### K-d. Timing protocol

- **Recommended:**
  1. The console fetches the verdict (and the CoE entry, for citations) and renders it hidden.
  2. Only then does it call `POST /views`. When the token returns, it reveals the case.
  3. A click on a decision sends `POST /decisions`.
- **Measures:**
  - the server's `decision_ms` (token issued to decision received) stays the binding measure (S4.1 A-e). It includes one loopback round trip, a few milliseconds;
  - `client_ms`: from reveal to click, using the browser's monotonic clock (`performance.now()`);
  - **new: `client_hidden_ms`**: how long the tab was hidden or out of focus during the case (Page Visibility API). The analysis can flag or exclude cases where a participant left the screen. It is stored beside the decision and never changes `decision_ms`.
- A reload or a reopened case issues a new view token; reopening is already recorded (S4.1).

### K-e. Study support: queue, blinding, chosen service

- **Recommended, all additive to the API:**
  - **Queue:** `GET /v1/queue` returns the cases assigned to the calling key, in order, with whether each is decided. Assignments come from an admin-written `assignments.json` (key ID to an ordered list of run IDs), mounted read-only. The E4 Latin square is generated into this file later, once the IRB protocol fixes the number of cases. The console shows only "case 3 of 12".
  - **Blinding:** a key created with `--blind` gets verdict, queue and decision responses with `variant` set to null. The participant cannot see Full or noExpl even in the browser's developer tools. Run IDs and incident IDs are opaque hashes already.
  - **Chosen service** (for "correct interpretation"): on reject, the participant may pick the service they believe is the root cause from the ranked list, or "none of these". On accept, the chosen service is the top-ranked one. New optional field `chosen_service` on the decision.
- **Trust** is measured by the IRB-approved questionnaire outside the console. A per-case trust item can be added in E4 preparation if the approved protocol asks for one.
- (b) Blinding by the console only (the API still returns the variant). Less code, but weaker.

### K-f. Simulated-HITL mode

- **Recommended:** `bin/simulate_hitl.py`, a scripted reviewer that drives the real API flow over HTTP (view token, then decision) for every run whose verdict requests a human (PROVISIONAL or NON_CONVERGED) in a campaign.
  - **Policies that read no labels:**
    - `accept` (the default): accept the top-ranked service;
    - `escalate`: escalate everything;
    - `confidence`: accept at or above a threshold given on the command line (no default), escalate below it.
  - **Reviewer think time** comes from the price book's human review time, so the simulation exercises timing at realistic scale without waiting for real. An injected clock makes it instant in tests and dry runs.
  - Simulated decisions are tagged: the key is created with `--simulated`, and every entry it writes carries `simulated: true`, so analysis can never mix them with human decisions.
- **What it is for:** exercising the instrument end to end (tokens, ledger, timing, queue) before any participant, and recording the HITL decisions of evidence runs. It does not change any metric: CpR keeps charging the fixed human time (S4.9 M-c).

### K-g. API changes and versioning

- **Recommended:** additive only, so existing clients keep working:
  - `GET /v1/queue`;
  - `chosen_service` and `client_hidden_ms` on `DecisionIn` and `DecisionOut`;
  - `--blind` and `--simulated` key attributes, with `simulated` in the ledger entry;
  - `API_VERSION` becomes `api-v1.1`, the committed spec is regenerated, and the drift test is kept.
- **Ledger:** the new fields are optional. The decisions ledger's `REQUIRED_FIELDS` do not change, so older entries still verify.

### K-h. Security

- **Recommended:**
  - strict Content-Security-Policy from nginx: `default-src 'self'`, no inline scripts or styles, `frame-ancestors 'none'`;
  - the API key is typed in once per session and kept in `sessionStorage`, never in the URL, `localStorage` or a cookie;
  - nginx proxies only `/v1/` and `/health`, so the console's origin exposes nothing else;
  - all rendered text is inserted as text, never as HTML, because narratives and evidence contain model output and log lines;
  - the console container is read-only, runs as non-root, and is on the `front` network only.

### K-i. Feature flag, files and tests

- **Flag:** `HELIOS_ENABLE_CONSOLE` in `helios/api/__init__.py`. When it is off, `/v1/queue` returns 404 and compose leaves the console out (profile).
- **Files:**
  - `console/` (`index.html`, `app.js`, `timing.js`, `render.js`, `api.js`, `console.css`);
  - `deploy/nginx.conf`, plus the `console` service in `deploy/compose.yaml`;
  - `bin/simulate_hitl.py`;
  - API additions in `helios/api/`.
- **Tests:**
  - **JavaScript:** pure functions (timing state machine, citation resolution, rendering to text nodes, blinding display) tested with Node's built-in runner (`node --test`), which needs no packages. A new CI job runs it (GitHub runners have Node).
  - **Python:** queue, blinding, the new fields, the simulated reviewer with an injected clock, and the drift test.
  - **Compose test:** the nginx image is pinned, the CSP header is set, and the console is published on loopback only.
- (b) Browser end-to-end tests with Playwright in CI: strongest, but they add a browser download to CI. Recommended instead: the walk-through (K-j) is done in a real browser once and recorded.

### K-j. Walk-through and timing verification (done-when)

- **Recommended**, on build data only, through compose:
  1. A queue of 8 cases for a blind reviewer key, interleaved: 4 HELIOS-Full and 4 HELIOS-noExpl runs, all from the OTel build campaign `camp_v3`, which has both variants. The API serves one campaign at a time.
  2. Walk through it in a real browser:
     - Full cases show the narrative and expandable citations; noExpl cases show none;
     - the variant is never shown, nor present in the responses;
     - one reject is made with a chosen service;
     - one case is left in a hidden tab, to check `client_hidden_ms`.
  3. **Timing check:**
     - for every decision, `decision_ms` is at least `client_ms`, and exceeds it by no more than a small round-trip margin;
     - one case is held for a fixed, measured interval, and both measures match it.
  4. Run `simulate_hitl.py` over every human-requested run in `camp_v3c`. The decisions ledger verifies, and the simulated entries are all tagged.
  5. Screenshots and figures go into §7.

## 4. Deviation entry

- **Recommended: none.** E-H7 is exploratory and its pre-registered measures (correct interpretation, time to decision, trust) are unchanged:
  - `chosen_service` and `client_hidden_ms` give the study more precise inputs;
  - the binding timing measure is still the server's `decision_ms`.
- If the E4 protocol later uses `client_hidden_ms` as an exclusion rule, that rule goes into the IRB protocol and the OSF addendum before the study.

## 5. Out of scope (E4 or Stage B)

- the Latin-square generator and participant scheduling (E4, after IRB approval);
- the trust questionnaire (IRB survey instrument);
- live incidents and remediation actions (Stage B);
- multi-tenant administration (Stage B).
