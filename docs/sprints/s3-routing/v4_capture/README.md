# OTel v4 held-out capture: record

2026-11-07 · corpus `otel_heldout_v4` · design `s3_otel_fix_design.md` decision O-d · deviation entry 76 · row S2-M8-ENG06

## Result

- 36 of 36 cases captured (9 fault types × 4 repetitions), v3 protocol, demo pinned as in v3.
- `capture_campaign.py verify`: ground-truth signature OK; 36 intact (window hash and content seal), 0 not.
- Digests (SHA-256):
  - `data/otel/heldout_v4_manifest.json`: `22248602f70810a45b8a96d0e26d25685a7dd88c5a84776f7bfe5a603d269e6c`
  - `data/otel/ground_truth_heldout_v4.json`: `3ea8cf685fde8d03ec826afe95f28ad7164ac94808a6ccd1345a8da31c0ae705`
- Nothing has read the cases since capture. Only the validation tool reads them, once (step 5 of the plan).

## Conditions and caveats

1. **Load generator memory raised to 3 GB.** The first two attempts failed: Locust timed out at the container's 1.5 GB limit. The limit was raised at runtime (`docker update --memory 3g --memory-swap 3g load-generator`), not in the pinned compose file. During the capture the generator used at most 2.98 GB.
2. **Traffic checked against v3 before each part** (`traffic_check.sh`; server and consumer calls per second, 2 min windows). v3's 63 cases had minimums of 2.5 (frontend-proxy) and 4.8 (frontend).
   - Part 1: 2.52 and 4.97.
   - Part 2: 2.6–3.2 and 5.0–6.1.
   - Locust reports about 6.5 failures a second throughout. They come from the demo's `WebsiteBrowserUser` (`no attribute 'tracer'`), whose tasks send no requests. Same pinned image as v3.
3. **Another project's containers (tessera) ran during the capture**, by owner decision. One-minute load average: mean 3.3, max 16.8 in part 1; mean 4.0, max 11.0 in part 2. tessera's database container used more than 10% CPU in 16 of 107 samples (part 1) and 3 of 26 (part 2). Samples every 5 min: `machine_load_part1.csv`, `machine_load_part2.csv`.
4. **Interrupted once.** At 15:06 UTC every demo container stopped within the same second; the cause is unknown. It was not memory (no container out of memory; Docker and tessera stayed up). The campaign failed waiting for flagd to switch `adFailure` off in case 30.
   - Cases 1–29 were already captured and labelled and are unaffected.
   - Case 30 was never labelled. The campaign keeps only labelled cases, so it was captured again from the start.
   - The containers were restarted in place (keeping the 3 GB limit), traffic rechecked (item 2), and the campaign resumed: cases 30–36 in part 2, ending 17:58 UTC.
