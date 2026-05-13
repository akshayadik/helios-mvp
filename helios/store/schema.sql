-- HELIOS result store — schema-draft-v0.1
-- Source: execution plan §3.6.3 + §5.1 run-level inclusion criteria
-- Tagged: schema-draft-v0.1 (will become v1.0 at OSF Stage 5 freeze)
--
-- All columns mirror PipelineVerdict fields. variant_config_hash and
-- snapshot_hash enforce C1 inclusion criteria at query time (§5.1).

CREATE TABLE IF NOT EXISTS result_row (
    run_id              VARCHAR     NOT NULL,
    incident_id         VARCHAR     NOT NULL,
    variant_config_hash VARCHAR     NOT NULL,   -- 64-char SHA-256 hex (VCLManifest)
    snapshot_hash       VARCHAR     NOT NULL,   -- 64-char SHA-256 hex (UEGCSnapshot)
    pipeline            VARCHAR     NOT NULL,   -- dpipe | gpipe | lpipe
    evaluation_phase    VARCHAR     NOT NULL,   -- exploratory | confirmatory
    ranked_candidates   JSON        NOT NULL,   -- ordered list of service names
    hr_at_3             DOUBLE      NOT NULL,
    cpr                 DOUBLE      NOT NULL,
    latency_ms          DOUBLE      NOT NULL,
    token_count         BIGINT      NOT NULL,
    narrative           TEXT        NOT NULL,
    schema_version      VARCHAR     NOT NULL    DEFAULT 'schema-draft-v0.1',
    created_at          TIMESTAMP               DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id)
);

-- Schema version registry — tracks deployed schema tags for audit trail
CREATE TABLE IF NOT EXISTS schema_tag (
    tag         VARCHAR     NOT NULL PRIMARY KEY,
    applied_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_tag (tag)
VALUES ('schema-draft-v0.1')
ON CONFLICT (tag) DO NOTHING;
