# HELIOS sprints

One folder per sprint for the whole product: Stage A (S0–S5, evidence, analysis) and Stage B. Each folder holds the sprint's **plan** (written ahead) and, when the sprint closes, its **exit report**.

**Sources of truth.** This folder is the sprint-level view. Task steps and "done when" details stay in `docs/tracking/helios_task_breakdown.md`; schedule, principles and decisions in `docs/tracking/helios_e2e_product_plan_2026-10.md`; task status in `docs/tracking/helios_mvp_tracking.md`. If a sprint plan and the breakdown disagree, the breakdown wins and the plan is corrected.

---

## Sprints

| Sprint | Folder | Planned window | Milestone | Exit tag | Status |
|---|---|---|---|---|---|
| S0 Foundation | [`s0-foundation/`](s0-foundation/) | 2–13 Nov 2026 | S2-M5 | `rb-s0-exit` | **Closed 2026-10-24** · [exit report](s0-foundation/exit_report.md) |
| S1 Data and graph | [`s1-data-graph/`](s1-data-graph/) | 16 Nov – 4 Dec 2026 | S2-M6 | `rb-s1-exit` | **Closed 2026-10-27** · [exit report](s1-data-graph/exit_report.md) |
| S2 Reasoning, consensus, narratives | [`s2-reasoning/`](s2-reasoning/) | 7–25 Dec 2026 | S2-M7 | `rb-s2-exit` | **Next** (plan refreshed 2026-10-27) |
| S3 Routing and learning | [`s3-routing/`](s3-routing/) | 4–15 Jan 2027 | S2-M8 | `rb-s3-exit` | Planned |
| S4 Product shell and evaluation tooling | [`s4-product-eval-tooling/`](s4-product-eval-tooling/) | 18–29 Jan 2027 | S2-M9 | `rb-s4-exit` | Planned |
| S5 Integration and freeze | [`s5-integration-freeze/`](s5-integration-freeze/) | 1–12 Feb 2027 | S2-M10 | `build-freeze` | Planned |
| E Evidence collection | [`e-evidence/`](e-evidence/) | 15 Feb – 12 Mar 2027 | S2-M11 | `rb-e-exit` | Planned |
| A Analysis | [`a-analysis/`](a-analysis/) | 15–31 Mar 2027 | S2-M12 | `results-ready` | Planned — **results ready 31 March** |
| Stage B Full product | [`stage-b/`](stage-b/) | 15 Feb – end Jul 2027 | S3-M13 … S3-M17 | `rb-b1-exit` … `rb-b5-exit` | Planned |

The exit tags for E, A and Stage B are proposed names; each is fixed in that sprint's plan before it starts.

## Capacity at a glance

Effort is the sum of the breakdown's task estimates, in working days, against the working days in the window.

| Sprint | Planned effort | Working days | Note |
|---|---|---|---|
| S1 | 16 | 15 | Over by one day; started early on 2026-10-24 (owner), so about 30 working days are available |
| S2 | 15½ | 15 | Tight; S2.9 rater training also needs the raters' time |
| S3 | 9 | 10 | Four of the five tasks are Tier 2 |
| S4 | 13½ | 10 | Over by 3½ days; Tier-2 items (S4.4–S4.7) are the first to move to Stage B |
| S5 | 8 | 10 | Two days of slack before the freeze |

Rule from the plan: if time is short, Tier 2 moves to Stage B; Tier 1 is never rushed, and the frozen evidence build is never touched.

---

## Folder conventions

```
docs/sprints/
  README.md                 this index
  s<N>-<name>/
    plan.md                 written before the sprint starts; updated at sprint start
    exit_report.md          written at the exit gate
```

- **Plan** (`plan.md`): goal; window and capacity; entry conditions; task table (ID, tier, tracking row, effort, dependencies, done when); owner items; expected deviation entries; exit criteria; risks.
- **Exit report** (`exit_report.md`), written as part of the exit gate, with these sections:
  1. Exit criteria — met / not met, with evidence.
  2. Gate results on the tagged commit.
  3. What the sprint delivered — task, tracking row, SHA, deviation entries.
  4. Retrospective — plan vs actual; decisions and why; what went wrong and what changed because of it; design-science notes (build–evaluate episodes for Chapter 4).
  5. Carried over — open items with owners and dates.
- At each exit, also update the **Status** column above and the documents listed in `docs/tracking/tracking_documents_register.md` whose update trigger the sprint hit.
- Sprint write-ups that other documents (or an OSF deposit) already cite by path stay in `docs/tracking/` and are linked from the plan, not moved.

**Path note.** The annotated tag `rb-s0-exit` names the S0 exit report at its first path, `docs/tracking/s0_exit_report.md`; it moved here on 2026-10-24 (tags are never rewritten).
