"""HELIOS-noRouter over the OTel build cases; CoE entries kept in scratch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from bin.log_deviation import load_key
from bin.mahc_build_run import CACHE_PATH, _CacheOnlyClient
from bin.router_build_run import _CountingLedger
from helios.consensus.params import load_mahc_params
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.vcl import get_variant, set_current_manifest

out = Path(sys.argv[1])
out.mkdir(parents=True)
manifest = get_variant("HELIOS-noRouter")
set_current_manifest(manifest)
key = load_key()
captures = Path("data/otel/build_v3")
orch = RunOrchestrator(
    manifest=manifest,
    captures_dir=captures,
    db_path=out / "otel.duckdb",
    registry_path=out / "reg.jsonl",
    reconciliation_path=out / "rec.jsonl",
    exclusion_ledger=_CountingLedger(),
    hmac_key=key,
    lpipe_client=_CacheOnlyClient(OLLAMA_BASE_URL, MODEL_NAME),
    lpipe_cache=ResponseCache(CACHE_PATH),
    mahc_params=load_mahc_params(),
    coe_path=out / "otel.coe.jsonl",
)
orch.run(captures)
print("entries", sum(1 for _ in (out / "otel.coe.jsonl").open()))
