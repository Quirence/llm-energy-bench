# Project Status

Last updated: 2026-09-28

## Current Milestone

M1 — Measured Pilot. The implementation is in final stabilization on PR #17;
no publishable dataset exists yet.

## Done

- The Python 3.12 CLI implements `doctor`, `run`, and `report` with stable exit
  codes and 295 Windows/Linux hardware-independent tests.
- Strict TOML and prompt contracts, Ollama streaming/TTFT, full-GPU placement,
  request-scoped NVML telemetry, power-source fallbacks, atomic artifacts,
  privacy guards, and aggregate reports are implemented.
- The pilot model is pinned to Ollama 0.34.2 and digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`.
- Schema v2 records four excluded warm-ups. The first is a cold-start
  exclusion; the minimum cached count from the next three is the auditable
  template floor.
- At most one cache token above that floor is accepted for the unique marker
  boundary. Raw, cached, and uncached prompt-token counts remain distinct.
- A model load longer than 100 ms in a cache-floor warm-up or measured request
  is invalid and aborts the launch; runtime failures also abort instead of
  contaminating later requests.
- Validation fails closed on unknown schemas and independently checks frozen
  runtime/digests, placement, warm-up floor, request counts, manifest counters,
  hashes, telemetry order/coverage, cache excess, load duration, and energy.
- Reports exclude entire invalid runs and rank configurations only within one
  `host_id × prompt category` block.
- Contributions from Qcsteeven and Dimas are integrated and attributed in
  `docs/project-state-for-owner.md`. Their later hardware observations are
  preserved separately as diagnostic evidence.

## In Progress

- PR #17 must receive collaborator approval and green Windows/Linux CI after
  the final stabilization commits are pushed.
- The 2026-09-28 RTX 5060 preflight passed NVML, digest and full-placement
  checks but found Ollama 0.34.4 instead of the frozen 0.34.2. The host must use
  the frozen runtime, or the protocol version must be amended for every host
  before any publishable pilot is launched.
- PRs #18, #19, and #22 were reviewed and closed without merge:
  #18 can draw a formal conclusion from invalid/incomparable campaigns; #19
  silently substitutes an RTX 4060 Ti for the frozen RTX 4060 host; #22 is
  stacked on #19 and includes a calibration launch contaminated by a model
  reload. Their useful requirements/evidence are preserved in Issues and docs.

## Next Acceptance Gate

1. Merge PR #17 by squash after one collaborator approval and both CI jobs.
2. Tag the exact merge commit `pilot-v1-code`.
3. Have Quirence and the second primary-host owner pull that tag and execute
   the committed pilot config without code or protocol changes.
4. Accept only runs with `validation.json: ok=true` and all 18 measured
   requests valid.
5. Freeze all four benchmark model digests before enabling `benchmark-v1`.

## Open Research Work

- RTX 5060 publishable pilot and three independent calibration launches.
- A confirmed second primary GPU. The original protocol says RTX 4060 desktop;
  the observed RTX 4060 Ti remains a distinct observation host until an
  explicit protocol amendment is reviewed.
- A corrected implementation of the rank-inversion analysis after clean,
  compatible campaign data exists. PR #18 is not the frozen implementation.
- External wattmeter validation remains outside MVP; all reported energy and
  cost values are GPU-only estimates.

## Latest Validated Run

No publishable run yet. RTX 5060 Laptop, RTX 4060 Ti, and GTX 1080 local runs
were useful diagnostics, but they predate the final schema-v2 tag or contain
known validity failures and therefore are excluded from the research dataset.
