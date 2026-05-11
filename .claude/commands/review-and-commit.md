/review-and-commit $ARGUMENTS
Run full pre-checkin protocol for HELIOS:
1. Reproducibility Guard
2. Research Compliance + Flag Guard (auto via PreToolUse)
3. Run relevant pipeline tests + metrics-evaluator (scoped)
4. Generate commit message with deviation log (custom format)
5. Optional: /compact-research-session
Then ask for final "git commit -m '...' -n" approval.