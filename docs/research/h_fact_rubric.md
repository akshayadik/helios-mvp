# H_fact rating rubric

**Status:** draft for rater training (S2.9). Frozen by its SHA-256 once training reaches κ ≥ 0.7, then deposited with OSF deposit 2; no change after confirmatory labelling starts. Design: `docs/sprints/s2-reasoning/s2_9_rubric_design.md`. Definition: deviation entry 65.

## What you are judging

You will see one **claim** at a time: a single sentence from an incident narrative written for an on-call engineer, with the **evidence it cites** directly underneath. Above it is a context line naming the top three suspect services; that line is not rated.

Judge **only whether the cited evidence supports the claim**, word for word. The claim is judged against the evidence on the card, never against the fault label or against what you think the real cause was. A claim can be supported even if the service it names turns out not to be the culprit.

Each claim gets one verdict:

- **Supported** — every part of the sentence is backed by the evidence it cites.
- **Unsupported** — at least one part is not. Then choose the **first** category below that applies, and add a one-line note if it helps.

Some claims are deliberately wrong checks mixed in to measure attention. They look exactly like real claims. Judge every claim the same way.

## Error categories (check in this order)

1. `numeric_drift` — a number in the sentence is not the number in the evidence (beyond the rounding the sentence states), or its unit is wrong (ms written as s, a count as a percentage).
2. `entity_mismatch` — the sentence names a service the evidence is not about, or reverses who calls whom (caller and callee swapped), or ranks a service at a position the fused verdict does not give it.
3. `directional_inversion` — the sentence says something rose when the evidence shows it fell, or the reverse.
4. `log_quote_mismatch` — the quoted text is not, word for word, in the logged template shown on the card.
5. `missing_citation` — the card says "evidence not found", or none of the cited items is the kind of evidence the claim needs.

## Claim kinds and what "supported" means

| Kind | Supported when |
|---|---|
| `ranking` | The fused verdict card ranks that service at that position (top, second, third). |
| `shift` | The cited metric item is the same service and the same signal (errors, latency, resource use); the before and after values match the card in the same unit, at the precision the sentence uses; the direction word (rose, fell, …) matches the change. "Rose sharply" without numbers needs only the right service, signal and direction. |
| `call_structure` | The cited call-graph item holds that edge in that direction (the caller is the one that calls); a stated share (for example 94%) matches the card. |
| `log_message` | The quoted words appear, in that order and word for word, in the logged template on the card. Masked parts such as `<NUM>` or `<DUR>` stand for any value and count as written. |
| `contradiction` | The named pipeline (D-pipe, G-pipe or L-pipe) ranks the named service first on its card, and the fused verdict's first service is the one the sentence names. |
| `verification_step` | The check targets one of the top three suspects or a service on a cited card; the kind of check matches the evidence (metrics for a metric card, logs for a log card, calls for a call-graph card); any time lies inside the incident window. These are suggestions, not facts: judge only whether they are grounded in the cited evidence. |

## Edge cases

- **Rounding.** "About 900 ms" for 897 ms is supported; "900 ms" for 870 ms is `numeric_drift`. The sentence's own precision sets the tolerance: "0.42 to 0.94" must match to two places.
- **Units shown by a metric name.** Some resource cards show the metric name instead of a unit (for example `container_cpu_utilization_ratio`); a sentence that says "cpu use" for it is fine.
- **Levels that did not change.** If before and after are equal on the card, any rise or fall is unsupported (`directional_inversion`).
- **Several cards.** A claim citing several items is supported if the items together back every part of it.
- **Masked log tokens.** `connection pool exhausted after <DUR>` supports the quote "connection pool exhausted after"; it does not support "connection pool exhausted after 30s" (a value the template does not show).
- **Unsure.** If you cannot tell, decide on the evidence in front of you and say why in the note; do not look anything up.

## Worked examples

(Filled from build data: one supported and one planted example per kind, each with its evidence card and the reason.)
