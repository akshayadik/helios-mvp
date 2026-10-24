# Hallucination Scoring Protocol (HELIOS)

Superseded (S0.7, 2026-10-24): the earlier percentage formula and κ > 0.75 target on this page are withdrawn.

Hallucination is measured as H_fact (unsupported atomic claims / all claims in the published narrative) and H_struct (agent tool calls or outputs failing schema validation / all of them), per case. Labelling follows the approved Ch3 inter-rater protocol: two raters blind to variant, Cohen's κ ≥ 0.7, third adjudicator below that, raters calibrated on 50 instances first. Full definition: `docs/tracking/metric_contract.md` §5.
