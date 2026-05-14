---
name: pipeline-tester
description: Verifying the integrity and schema compliance of G-pipe and L-pipe modules.
---
# Instructions
- **Pipeline Gating:** Ensure every pipeline entry point is decorated with `@gated_by`.
- **Schema Compliance:** All outputs must strictly adhere to the Pydantic models in `helios/schemas/`.
- **Determinism:** Verify that snapshots result in stable hashes and that LLM outputs follow Protocol A (temperature=0).
- **Test Coverage:** Run `tests/test_pipelines.py` after any change to pipeline logic.
