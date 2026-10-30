-- HELIOS result store — schema-draft-v0.5
-- Source: execution plan §3.6.3 + §5.1 run-level inclusion criteria
-- Tagged: schema-draft-v0.5 (will become v1.0 at OSF Stage 5 freeze)
--
-- result_row mirrors PipelineVerdict (helios/schemas/verdict.py, S1.8).
-- variant_config_hash and snapshot_hash enforce C1 inclusion criteria at
-- query time (§5.1). Scores against ground truth (HR@k, MRR) are not stored
-- here: they are computed after dispatch by the scoring path (S1.9).
--
-- PK is (run_id, pipeline): one row per pipeline per incident run.
-- run_id is a per-incident UUID shared by all three pipeline verdicts.
-- A database created before v0.5 keeps its rows in result_row_v04
-- (ResultStore._archive_pre_v05); they are never rewritten.

CREATE TABLE IF NOT EXISTS result_row (
    run_id              VARCHAR     NOT NULL,
    incident_id         VARCHAR     NOT NULL,
    variant_config_hash VARCHAR     NOT NULL,   -- 64-char SHA-256 hex (VCLManifest)
    snapshot_hash       VARCHAR     NOT NULL,   -- 64-char SHA-256 hex (UEGCSnapshot)
    pipeline            VARCHAR     NOT NULL,   -- dpipe | gpipe | lpipe
    evaluation_phase    VARCHAR     NOT NULL,   -- exploratory | confirmatory
    status              VARCHAR     NOT NULL,   -- ranked | abstained | skipped | failed
    ranked_candidates   JSON        NOT NULL,   -- ordered list of service names
    candidate_scores    JSON        NOT NULL,   -- the pipeline's own score per candidate
    mu                  DOUBLE,                 -- confidence in the top-1; NULL = no estimator
    sigma               DOUBLE,                 -- standard deviation of mu; NULL = unknown
    prompt_tokens       BIGINT      NOT NULL,
    completion_tokens   BIGINT      NOT NULL,
    cpu_ms              DOUBLE      NOT NULL,
    gpu_ms              DOUBLE      NOT NULL,
    latency_ms          DOUBLE      NOT NULL,
    narrative           TEXT        NOT NULL,
    prompt_version      VARCHAR,
    decision_hash       VARCHAR     NOT NULL,   -- PipelineVerdict.compute_decision_hash()
    schema_version      VARCHAR     NOT NULL    DEFAULT 'schema-draft-v0.5',
    created_at          TIMESTAMP               DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, pipeline)
);

-- Schema version registry — tracks deployed schema tags for audit trail
CREATE TABLE IF NOT EXISTS schema_tag (
    tag         VARCHAR     NOT NULL PRIMARY KEY,
    applied_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.1')
ON CONFLICT (tag) DO NOTHING;

INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.2')
ON CONFLICT (tag) DO NOTHING;

INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.3')
ON CONFLICT (tag) DO NOTHING;

-- schema-draft-v0.3: consensus verdict table
CREATE TABLE IF NOT EXISTS consensus_verdict (
    incident_id              VARCHAR NOT NULL,
    variant                  VARCHAR NOT NULL,
    top_candidates           VARCHAR NOT NULL,  -- JSON array string
    borda_scores             VARCHAR NOT NULL,  -- JSON object string (per-incident relative; see candidate_universe_size)
    candidate_universe_size  INTEGER NOT NULL,  -- |all_candidates| for this incident; enables post-hoc normalisation
    consensus_rank           INTEGER NOT NULL,
    fusion_algorithm         VARCHAR NOT NULL,
    fusion_algorithm_sha     VARCHAR NOT NULL,
    cpr                      DOUBLE  NOT NULL DEFAULT 0,
    pipeline_row_count       INTEGER NOT NULL,
    run_id                   VARCHAR NOT NULL,
    timestamp_utc            VARCHAR NOT NULL,
    PRIMARY KEY (incident_id, variant)
);

-- schema-draft-v0.4: result_row.cpr renamed to mrr (it holds reciprocal rank;
-- CpR is cost per resolution, see docs/tracking/metric_contract.md).
-- Databases created before v0.4 are migrated by ResultStore._migrate_cpr_to_mrr.
INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.4')
ON CONFLICT (tag) DO NOTHING;

-- schema-draft-v0.5 (S1.8): result_row carries the verdict contract — status,
-- candidate scores, mu, sigma, cost (tokens, CPU and GPU time) and the
-- decision hash; hr_at_3, mrr and token_count left the row (scores move to
-- the S1.9 scoring path; tokens are split into prompt and completion).
INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.5')
ON CONFLICT (tag) DO NOTHING;

-- eval-score-v1 (S1.9): accuracy scores, computed after dispatch by the
-- scoring path (helios/evaluation/scoring.py) from result_row and
-- consensus_verdict joined to the ground truth. Kept apart from the verdicts:
-- no pipeline reads this table. The label itself is never stored, only the
-- rank it was found at and the SHA-256 of the ground-truth file.
CREATE TABLE IF NOT EXISTS eval_score (
    run_id              VARCHAR     NOT NULL,
    incident_id         VARCHAR     NOT NULL,
    variant_config_hash VARCHAR,                -- NULL for fused lists (keyed by variant)
    list_kind           VARCHAR     NOT NULL,   -- fused | pipeline
    source              VARCHAR     NOT NULL,   -- variant name (fused) or dpipe | gpipe | lpipe
    source_status       VARCHAR     NOT NULL,   -- fused, or the verdict status (ranked | abstained | failed)
    list_length         INTEGER     NOT NULL,
    ground_truth_rank   INTEGER,                -- 1-based; NULL = absent from the list
    hr_at_1             INTEGER     NOT NULL,
    hr_at_3             INTEGER     NOT NULL,
    hr_at_10            INTEGER     NOT NULL,
    avg_at_5            DOUBLE      NOT NULL,
    mrr                 DOUBLE      NOT NULL,
    corpus              VARCHAR     NOT NULL,   -- build | pool | captures
    ground_truth_sha256 VARCHAR     NOT NULL,
    scoring_version     VARCHAR     NOT NULL,
    scored_at           TIMESTAMP               DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, list_kind, source)
);

INSERT INTO schema_tag (tag)
VALUES ('eval-score-v1')
ON CONFLICT (tag) DO NOTHING;

-- trigger-v1 (S2.1): the shared detection trigger each run handed to every
-- system (helios/telemetry/trigger.py), and per-pipeline wall-clock times.
-- TTCD and TTT are measured from handover_unix (deviation entry 46). The
-- baseline harness (S4.8) reads the same trigger_row, so every system gets
-- the identical trigger.
CREATE TABLE IF NOT EXISTS trigger_row (
    run_id              VARCHAR     PRIMARY KEY,
    incident_id         VARCHAR     NOT NULL,
    variant_config_hash VARCHAR     NOT NULL,
    trigger_time_s      DOUBLE      NOT NULL,   -- recorded-time instant, epoch seconds
    suspects            VARCHAR     NOT NULL,   -- JSON list, strongest first
    context             VARCHAR     NOT NULL,   -- JSON list of out-of-scope services
    source              VARCHAR     NOT NULL,   -- threshold | fallback | external
    detector_hash       VARCHAR     NOT NULL,
    seeds_from_trigger  BOOLEAN     NOT NULL,
    handover_unix       DOUBLE      NOT NULL,
    stored_at           TIMESTAMP               DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS timing_row (
    run_id              VARCHAR     NOT NULL,
    pipeline            VARCHAR     NOT NULL,
    started_unix        DOUBLE      NOT NULL,
    published_unix      DOUBLE      NOT NULL,
    PRIMARY KEY (run_id, pipeline)
);

INSERT INTO schema_tag (tag)
VALUES ('trigger-v1')
ON CONFLICT (tag) DO NOTHING;

-- gpipe-evidence-v1 (S2.2): the graph facts behind a pipeline's top suspects
-- (wait share pooled from callers, leads, ghost edges, self-time shift), for
-- the narratives (IN1) and the RQ4 check. No label, no injection time.
CREATE TABLE IF NOT EXISTS evidence_row (
    run_id              VARCHAR     NOT NULL,
    incident_id         VARCHAR     NOT NULL,
    pipeline            VARCHAR     NOT NULL,
    evidence_json       VARCHAR     NOT NULL,
    PRIMARY KEY (run_id, pipeline)
);

INSERT INTO schema_tag (tag)
VALUES ('gpipe-evidence-v1')
ON CONFLICT (tag) DO NOTHING;
