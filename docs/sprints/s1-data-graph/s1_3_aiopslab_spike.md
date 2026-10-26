# S1.3 — AIOpsLab recording spike · report

**Task:** S1.3 (tracking S2-M6-RES02) · **Date:** 2026-10-27 · **Question:** does AIOpsLab join the Stage A confirmatory pool? Go means a D11 addendum before the freeze; no-go means Stage B, recorded. · **Recommendation: no-go for the pool; AIOpsLab moves to Stage B as an exploratory external-validity corpus** (owner to confirm) · **Feature flags:** none; recording only (`HELIOS_ENABLE_*` unaffected)

## What was done

| Step | Result |
|---|---|
| Tools | `kind` 0.33.0 and `helm` 4.3.1 (Homebrew), `kubectl` present. AIOpsLab cloned outside the repo (`../aiopslab`, commit `576c3f0`, 2026-10-19) with its own Python 3.11 environment |
| Cluster | AIOpsLab's ARM kind config: 1 control plane + 1 worker, Kubernetes v1.32.1; runs beside the OTel Demo within Docker's 16 GB |
| Problem | `network_delay_hotel_res-localization-1`: HotelReservation (DeathStarBench), a Chaos Mesh network delay on service `user` |
| Recording | AIOpsLab injects the fault right after deploying the app, and it stays on until an agent answers. To match our format, a driver deployed the app, ran the workload, recorded **5 min normal**, injected, recorded **5 min fault**, then recovered |
| Export and conversion | The cluster's Prometheus and Jaeger were reached through port-forwards and read with the HELIOS fetchers (traces in 60 s slices; per-container CPU rate and memory, `service_name` added; logs via `kubectl logs` limited to the window). Written as a TelemetryWindow under an opaque ID and sealed |
| Checks | `CaptureReader`: **intact** (window hash and content seal). UEG-C builds: 33 service nodes, 140 edges (call, structural, both causal kinds, KPI), and the faulty service is a node. **Fault visible:** `user` median span duration 265 µs before → 1,582 µs after the onset (6×); frontend and search unchanged. Window about 6.3 MB |

The cluster was deleted afterwards. The driver and converter are kept as spike notes (not repo code).

**Done-when:** the conversion to the sealed format works end to end. The decision follows.

## Why not the confirmatory pool

1. **Too few distinct root causes.** AIOpsLab's 29 localization problems are fixed scenarios, one fault location each:
   - **HotelReservation:** network delay, network loss, pod failure and pod kill all hit the same service, `user`. The others hit `geo` (misconfigured app, container kill) and `mongodb-rate` (revoked auth, unregistered user); wrong-binary takes a parameter.
   - **SocialNetwork:** `user-service` (scale to zero, unknown node), `nginx-thrift`, `url-shorten-mongodb`.
   - **Astronomy Shop:** 12 problems, the OTel Demo flags S1.2 already records (build data).
   - **Operator problems:** TiDB, no application service.

   That is about 6–8 root-cause locations, repeated rather than varied. Repetitions of one scenario are not independent cases, and a "most likely service" prior would score close to perfect. This is a stronger form of the concentration already flagged for RCAEval (S0.1 F2, validity T16).
2. **It is a live benchmark, not a recorded one.** The window, onset and workload had to be supplied by our own driver. AIOpsLab's own export is unusable as recorded data:
   - traces use a look-back from *now* and ignore the end time;
   - there is no trace limit, so Jaeger's default cap applies;
   - metric exports cover "the last N minutes".
3. **Reproducibility needs work before any confirmatory use:**
   - **Community node image:** the ARM cluster uses an unpinned community node image (`jacksonarthurclark/aiopslab-kind-arm:latest`).
   - **Unpinned installs:** OpenEBS is installed from an unpinned URL, and the Chaos Mesh and Prometheus Helm charts are not version-pinned.
   - **Kubernetes context:** AIOpsLab assumes the context `kind-kind`.
4. **Schedule and baselines.** A pool addition needs a D11 addendum, an OSF deposit-2 update, and the five RCAEval baselines rerun on converted windows. All of that falls before the mid-February freeze, for a few concentrated scenarios.

## What AIOpsLab is good for (Stage B)

- **A third application family.** DeathStarBench, alongside RCAEval's Online Boutique and Train-Ticket, for an exploratory generalisation check (validity T6).
- **Kubernetes-level faults** (scheduling, scaling, storage, auth) that RCAEval lacks.
- **A starting point already exists.** The driver plus converter work end to end; a Stage B task would turn them into repo tooling: pinned images and charts, our protocol, opaque IDs, signed labels.

## Findings for other tasks

- **Trace-capture defect (deviation entry 45).** Converting this window exposed a bug in HELIOS's Jaeger fetcher: every span was labelled with the queried service, so each span appeared several times, mostly under the wrong service (here 67,485 distinct spans in 363,019 rows). It is fixed on the S1.2 branch. The May OTel captures are affected (validity T17), and the S1.7 captures check is void.
- **Helm 4.** Helm 4.3.1 deployed AIOpsLab's Prometheus and Chaos Mesh charts without errors.
