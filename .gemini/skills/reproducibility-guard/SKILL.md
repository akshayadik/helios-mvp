---
name: reproducibility-guard
description: Enforcing HMAC chain integrity, Python 3.11.x constraints, and tracking schema rules.
---
# Instructions
- **HMAC Chain:** Forbidden from suggesting manual edits to `deviation_log.jsonl`. Always use `bin/log_deviation.py`.
- **Python Version:** Reject any suggestions for Python 3.12+ features.
- **Tracking Schema:** Enforce rules R1-R8 for all entries in `docs/tracking/helios_mvp_tracking.md`.
- **Secret Protection:** Never log or commit `DEVIATION_HMAC_SECRET`.
