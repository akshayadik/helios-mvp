# S2.9 — Rating rubric and blind labelling protocol (H_fact) · design

**Task:** S2.9 (tracking S2-M7-RES01) · **Date:** 2026-11-01 · **Status:** approved 2026-11-01 (builder check done; R-k to R-o answered) · **Depends on:** S2.8 (displayed narratives in CoE step N, entries 65–68), S2.7 (CoE ledger), S0.11 L2–L3 (rater 2 and adjudicator, due 30 Nov) · **Owner decisions:** marked *owner* (2026-11-01)

**Flag:** none of its own. The tool and the rubric are evaluation instruments, not product components: they read stored CoE entries and never run inside a variant. What they label is gated upstream (`coe_narrative`; HELIOS-noExpl has no narrative and is not labelled).

## 1. Intent

A-H7 asks whether HELIOS-Full's displayed narratives contain more unsupported claims than HELIOS-noLLM's. Entry 65 fixed what "supported" means: a displayed claim is supported if and only if the CoE items it cites exist and substantiate its entity, direction, magnitude and, for a log claim, its quoted text — judged against the evidence, never against the fault label. S2.9 builds what turns that definition into labels two humans can produce reliably and blind: a written rubric, a labelling set, a small web tool, a signed record of every label, and the training that proves the raters agree (κ ≥ 0.7) before any confirmatory narrative is labelled.

Since S2.8 every displayed claim has already passed the verifier, and Full and noLLM share one wording (entries 67–68). Raters are therefore expected to find almost nothing unsupported. That is a result, not a failure, but it breaks agreement statistics (§5.2) and shapes this design.

## 2. Owner decisions (2026-11-01)

| ID | Decision | By |
|---|---|---|
| R-a | **Raters:** 2 raters plus 1 adjudicator (the S0.11 model), with systems literacy (SRE, backend, DevOps or systems research); lay annotators misread p99 latency, units and caller–callee direction | owner |
| R-b | **Blinding:** raters never see the variant, the run, the case name or the fault label; arms appear only as masked codes inside the server | owner |
| R-c | **Layout B, one claim at a time:** each screen shows one claim with only the evidence it cites directly underneath, plus the code-filled header line for context (not rated). The rater cannot judge without the evidence in view | owner |
| R-d | **Claims shuffled across all narratives and both arms** (with the planted checks), so narrative length and claim mix cannot reveal the arm | owner |
| R-e | **Binary judgement:** Supported / Unsupported; Unsupported requires one error category: (1) numeric drift or unit error, (2) entity mismatch (wrong service, or caller and callee reversed), (3) directional inversion, (4) log quote mismatch, (5) missing or unresolvable citation. Optional one-line note | owner |
| R-f | **Planted claims** (known-corrupted, code-generated) in both training and confirmatory labelling; excluded from H_fact; they keep κ meaningful at near-zero prevalence and measure each rater's attention | owner |
| R-g | **Every Full and noLLM pool narrative is labelled** (240 cases × 2 arms = 480 narratives), as registered; about 20 hours per rater | owner |
| R-h | **Central server on the owner's machine**, reached by raters through the owner's tunnel (Tailscale, WireGuard, SSH tunnel or basic-auth HTTPS proxy). Raters use only a browser; code, data and ledger never leave the machine | owner |
| R-i | **Disagreements:** where the raters agree, the label stands; where they disagree on a real claim, the adjudicator decides without knowing who said what. The adjudicated set is primary; κ on the two raters' raw labels and H_fact per rater are reported beside it | owner |
| R-j | **Onboarding:** each rater first labels a short pre-scored calibration set showing a supported claim and each error category, with the answers shown afterwards | owner |
| R-k | **Arm leak by claim kind, accepted and disclosed:** HELIOS-noLLM has no L-pipe evidence, so log claims, log checks and "L-pipe ranks…" contradictions occur only in HELIOS-Full and can reveal the arm. Not hidden (dropping them would bias H_fact); reported as a limitation. What can be hidden is: the header line shows only the top-3 suspects (no confidence or state, which differ between arms). A **blinding check**: each rater guesses the arm for a small random sample of real claims; the hit rate is reported | owner |
| R-l | **Both raters are external** and independent of HELIOS; the owner is neither a rater nor present at disagreement reviews (so the owner's access to the server's sealed key does not touch the labels) | owner |
| R-m | **κ rule in phase E:** κ ≥ 0.7 → adjudicated disagreements are primary (R-i); κ < 0.7 → the adjudicator re-labels every real claim, as deposited in OSF deposit 1, and that set is primary. A rater below the planted-claim floor is paused and retrained; their labels in that sitting are relabelled | owner |
| R-n | **Separate signing key** for the annotations ledger (its own Ed25519 key pair; public key committed), so the deviation log's private key never sits in the long-running server | owner |
| R-o | **Shuffle seed derived from frozen inputs:** SHA-256 of the labelling set's sorted item list and the rubric hash (no new register block; the register in OSF deposit 1 stays as deposited); recorded in the set manifest and the deviation entry | owner |

Carried from entry 65: the rubric follows the evidence-based definition; the verifier's labels and machine report are reported beside the rater labels and never replace them.

## 3. Goals, non-goals, anti-goals

**Goals.** Labels for every displayed claim of every Full and noLLM pool narrative, from two blind raters, with κ ≥ 0.7 shown on training data first; an immutable, signed record of every label; H_fact per arm from the adjudicated labels; everything reproducible from frozen inputs and hashed for OSF deposit 2.

**Non-goals.** Judging whether the narrated culprit is the true root cause (HR@k does that). Rating prose quality, helpfulness or style. Labelling other variants (D, G and the rest are not in A-H7). Building the tunnel or user accounts beyond one key per person.

**Anti-goals** (would make this a failure even if it works): a rater can tell or infer the arm beyond the disclosed claim-kind leak (R-k); a label can be changed or deleted without trace; planted claims leak into H_fact; a rater sees another rater's labels; any pool data or ground truth reaches a rater's machine beyond the screen they are rating; the rubric changes after confirmatory labelling starts.

## 4. Constraints

- **Pool lock (D11).** Pool narratives exist only after tag `build-freeze`. Everything in S2.9 is built and trained on build data; the confirmatory labelling set is built after the tag, from the confirmatory CoE ledgers. Tool output in this sprint is counts only for pool data.
- **No ground truth.** The labelling set builder never opens a ground-truth file (entry 65); a test proves it.
- **Seeds.** The register is frozen in OSF deposit 1 (`research/osf/seeds.json`, never regenerated); the shuffle seed is derived from frozen inputs (R-o).
- **Rubric frozen before confirmatory labelling.** Its SHA-256 goes into OSF deposit 2 (S5.7). Any rubric change that alters what H_fact measures needs a deviation entry.
- **No new dependencies** unless needed: the server uses the Python standard library; the page is plain HTML and JavaScript served by it.
- Repository rules apply: feature-flag hooks, research-compliance literals, full gate, local merges only (no push).

## 5. Design

### 5.1 Rubric (`docs/research/h_fact_rubric.md`, hashed)

- **Unit:** one displayed claim (one sentence of a story, contradiction or verification slot, as stored in CoE step N). The header line is code-filled, shown as the top-3 suspects only (R-k), and not rated.
- **Supported**, per claim kind:
  - ranking: the cited fused verdict ranks that service at that position;
  - shift: the cited D-pipe item is the same service and channel, the stated before and after values match the evidence (within the stated precision) in the same unit, and the direction word matches the change;
  - call structure: the cited G-pipe item holds that edge in that direction (caller before callee) and, for a share, that percentage;
  - log message: the quoted text appears word for word in the logged template text of the cited log line;
  - contradiction: the named pipeline ranks the named service first in its cited item, and the fused verdict's first service is as stated;
  - verification step: the target service is a top-3 suspect or a cited neighbour, the check matches the cited evidence's kind (metric, log or calls), and any times lie inside the incident window.
- **Unsupported** if any of these fails; the rater picks the first category in R-e's order that applies.
- **Worked examples:** two per kind from build data (one supported, one planted per category), each with its evidence card and the reason.
- **Edge cases written down:** rounding ("about 900 ms" for 897), masked tokens in log templates (`<NUM>`, `<DUR>`), units shown by the metric name, "rose sharply" without numbers, a shift whose levels are equal.

### 5.2 Planted claims (R-f)

- **Why:** with real claims almost all supported, two raters can agree on 99% of claims and still score κ near zero or undefined (the prevalence paradox). Planted claims with known answers give both labels a real share and test whether raters catch errors.
- **Generation:** code takes a real claim and applies one corruption, giving a planted claim with a known category:
  1. numeric drift: move a stated number beyond the tolerance, or swap ms and s;
  2. entity mismatch: replace the service with another service of the same entry, or swap caller and callee;
  3. directional inversion: replace the direction word with its opposite;
  4. log quote mismatch: change or insert one word inside the quote;
  5. missing citation: cite an evidence ID that does not exist (the card shows "evidence not found").

  Every planted claim must be rejected by the S2.8 verifier with the matching reason (a test enforces this), and must read like a real claim of its kind.
- **Shares:** training, about a quarter of all claims shown; confirmatory, about one in ten. Raters are told that checks exist, not how many or which.
- **Key:** which claims are planted, their category and their source claim go in a sealed key file on the server; the browser never receives it.
- **Reporting:** per rater, detection rate per category and false-alarm rate on real claims. **Detection floor** *(Claude's call)*: 80% of planted claims caught per sitting; below it the rater is paused and retrained and that sitting's labels are relabelled (R-m).

### 5.3 Labelling set builder (`bin/labelling_set.py`)

- **Input:** one or more CoE ledger directories (signed, verified before use; S2.7) and the arms to include (Full and noLLM).
- **Steps:** verify each ledger; take step N's displayed claims and resolve each cited ID to an evidence card (ID, service, description, values with units, log template text, edge); build the planted claims (§5.2); give every item an opaque ID; shuffle all items with the derived seed (R-o); each rater's order is a further permutation keyed by the same seed and the rater's slot.
- **Outputs:**
  - `set.json`: what raters may see (opaque item ID, header line, claim sentence, evidence cards);
  - `key.json`: what they may not (item → arm, run, case ID, slot, claim index, planted flag and category);
  - a manifest with the SHA-256 of both, the seed, the rubric hash and the source ledger anchors.

  Both files stay on the server and are frozen once built (write-once, like capture seals).
- **Masking:** arm names, run IDs, case IDs and file paths never appear in `set.json`; a test scans for them. Service names stay (raters need them, as engineers would).

### 5.4 Labelling server (`bin/label_server.py`)

- **Binding:** listens on the loopback interface only; the owner's tunnel is the only way in.
- **People:** one secret key per person (R1, R2, adjudicator), issued by a CLI command and stored hashed; every request carries it; a wrong key gets nothing.
- **Rater flow (layout B):** next unlabelled item in the rater's order → claim card with the header line and evidence cards → Supported / Unsupported (+ category, + note) → next. A progress bar per session; "pause" ends a sitting. Each rater has their own order (§5.7) so the two raters do not see items in the same sequence.
- **Adjudicator flow:** only real claims on which R1 and R2 disagree, shown with both labels unattributed ("rater A", "rater B", in random order) and the same card; the adjudicator picks the final label and category.
- **Timing:** dwell time measured by the server between serving an item and receiving its label.
- **Revising labels** *(Claude's call)*: a rater may revise their own label (a newer ledger entry) until both raters have labelled that item; then it locks. Onboarding labels are kept apart from the labelling set.
- **What goes to the adjudicator** *(Claude's call)*: real claims with a verdict disagreement, and, for the category tables only, claims both raters marked Unsupported with different categories (these never change H_fact). In phase E with κ < 0.7, every real claim (R-m).
- **Blinding check (R-k):** after a sitting, a few already-labelled real claims are shown again with "Which narrator wrote this? A / B / can't tell"; answers are stored apart from labels.
- **Never sent to the browser:** the key file, other people's labels (except unattributed to the adjudicator), planted flags, arms.

### 5.5 Annotations ledger (`<set dir>/annotations.jsonl`)

- One entry per label: item ID, person, verdict, category, note, dwell time, server timestamp, set manifest hash. Changing a label means appending a newer entry; the latest entry per (item, person) counts.
- HMAC-chained per entry with an Ed25519-signed anchor, the same anchor-only mode as the CoE ledger (S2.7), signed with its own key pair (R-n): private key in the owner's `.env` beside the others, public key committed; verified by `bin/verify_ledgers.py` with that public key.
- Lives beside the labelling set on the server; never committed while it holds pool data (counts only until analysis).

### 5.6 Analysis (`helios/evaluation/rater_agreement.py`)

- **κ:** Cohen's κ between R1 and R2 on the binary label, over all items (real and planted) and separately over real claims only; category agreement on items both marked Unsupported. S4.9 reuses this function.
- **H_fact per arm:** unsupported real claims ÷ real claims displayed, on the adjudicated labels (R-i); per case for A-H7's paired sign test; also per rater as a sensitivity table.
- **Beside it:** the verifier's labels and machine report (entry 65), planted-claim detection per rater, dwell-time distribution (to spot rushing).

### 5.7 Training protocol (S2.9's done-when)

1. **Onboarding (R-j):** a pre-scored calibration set of about 40 claims from build data covering every kind and category; answers and reasons shown after each sitting.
2. **Training set:** 50 build-data narratives (25 HELIOS-Full, 25 HELIOS-noLLM; both build corpora), with planted claims at about a quarter: roughly 500 claims, about three hours per rater.
   - *Source (Claude's call):* a build run keeps signed CoE ledgers for HELIOS-Full (frozen narrator: local model, L-pipe answers from the cache only) and HELIOS-noLLM on all build cases; the narrator's dev and held-out cases may be reused (the narrator is frozen and labels never reach it).
   - *Selection (Claude's call):* stratified by claim kind so every kind appears (call-structure claims come almost only from the OTel captures), chosen by the derived seed; no case repeats across training rounds; plan for 2 rounds, a third only if κ is still below 0.7.
3. Both raters label it blind; compute κ; the owner and adjudicator review disagreements with the raters; revise the rubric (each revision committed, hashed and logged); relabel a fresh 50 until κ ≥ 0.7 on all items, reported also on real claims only.
4. Freeze the rubric (hash), record it in the tracking row, and put it in OSF deposit 2 before any confirmatory labelling.

### 5.8 Confirmatory labelling (phase E, after `build-freeze`)

Build the set from the confirmatory CoE ledgers (480 narratives, planted claims at about one in ten), label in sittings of about 50 minutes, adjudicate, verify the annotations ledger, then analyse. Not run in S2.

## 6. Deviation entry (drafted when the rubric freezes, before any confirmatory labelling)

One entry covering: planted claims and their exclusion from H_fact; claim-level shuffle across narratives and arms; the fifth error category (entry 65 listed four); adjudicated disagreements as primary when κ ≥ 0.7 and the deposited full re-label when κ < 0.7 (R-i, R-m); the derived shuffle seed instead of a new register block (R-o); the annotations signing key (R-n); the disclosed claim-kind leak and the blinding check (R-k); the frozen rubric hash.

## 7. Left to the builder

File and table names inside the set directory; page styling; key issuance UX; the exact corruption generators within §5.2's categories; how the onboarding answers are displayed; progress and pause behaviour.

## 8. Tracking and evidence

Row S2-M7-RES01 (IN_PROGRESS at start, DONE when κ ≥ 0.7 on training, rubric hash recorded, tool tested on fixtures). Rater training depends on rater 2 (due 30 Nov) and may run into early January; if so the row's training part is carried with a deviation reference and the S2 exit report says so.

## 10. Results

**PR 1 (instrument), built 2026-11-01** on branch `s2/rubric`. Row S2-M7-RES01 stays IN_PROGRESS: κ ≥ 0.7 needs both raters (rater 2 due 30 Nov).

| Part | Where |
|---|---|
| Annotations ledger, own Ed25519 anchor key (R-n) | `helios/labelling/annotations.py`; `bin/verify_ledgers.py --annotations` |
| Claim and evidence cards (top-3 header, template-only log cards, "evidence not found", context cards) | `helios/labelling/cards.py` |
| Planted claims, one corruption per category, each rejected by the S2.8 verifier for its reason | `helios/labelling/planted.py` |
| Labelling set: masked `set.json`, sealed `key.json`, derived seed (R-o), write-once, pool refused, no ground truth | `helios/labelling/sets.py`, `bin/labelling_set.py` (`--per-arm`, `--exclude-sets`, `--onboarding`) |
| κ, consensus (R-i, R-m), H_fact per arm, case and rater, planted-claim detection, blinding check | `helios/evaluation/rater_agreement.py` |
| Labelling server and page (layout B, loopback, a key per person in the link fragment, lock rule, adjudicator queue, onboarding answers, blinding question) | `helios/labelling/session.py`, `helios/labelling/page.html`, `bin/label_server.py` |
| Build ledgers, stratified training selection, onboarding set | `bin/labelling_runs.py`, `helios/labelling/training.py` |
| Rubric draft with worked examples from build data | `docs/research/h_fact_rubric.md` |

**Builder's calls while building** (all in the plan ledger): optional label fields validated by the ledger class; number corruptions scale values (no unit swap); an undefined κ counts as below 0.7; a new sitting after a 30-minute pause; raters may revisit a label until both have labelled it; the batch build tool signs CoE anchors with the CoE key, the server only with the annotations key; contradiction and verification-step cards add the pipeline ranking, fused verdict and incident window the verifier checks (found while writing the worked examples).

**Build data ready for training:** signed ledgers for HELIOS-Full and HELIOS-noLLM on both build corpora (1,116 entries, all verify with the public key, none excluded); training round 1 = 528 items (396 real claims from 25 + 25 narratives, 132 planted, 26–27 per category, every claim kind); onboarding = 38 items (18 real, 20 planted). Smoke test of the real server on a scratch copy: page served, keyless request refused, an item served without any arm, run or planted field, one label recorded.

**Gate:** full local gate green, coverage 95.83%.

**PR 2 (training, owner-led):** annotations key (`label_server.py keygen`), three people, tunnel; onboarding; rounds until κ ≥ 0.7; rubric frozen by hash; deviation entry of §6.
