# Project Status

Last updated: 2026-09-29

## Current Milestone

M2 — Two-GPU Study. The implementation is frozen at `pilot-v1-code`; the
primary RTX 5060 Laptop and RTX 4060 Ti pilot launches are ready to start.

## Done

- The Python 3.12 CLI implements `doctor`, `run`, and `report` with stable exit
  codes and 300 Windows/Linux hardware-independent tests.
- Strict TOML and prompt contracts, Ollama streaming/TTFT, full-GPU placement,
  request-scoped NVML telemetry, power-source fallbacks, atomic artifacts,
  privacy guards, and aggregate reports are implemented.
- The pilot model is pinned to Ollama 0.34.2 and digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`.
- Before any publishable data was collected, the two-host protocol was amended
  to the hardware actually available: RTX 5060 Laptop and RTX 4060 Ti desktop.
  GTX 1080 has a committed observation-only pilot config.
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
- PR #17 was independently approved, passed Windows/Linux CI, and was
  squash-merged as `0ffc091`. The immutable `pilot-v1-code` tag points exactly
  to that commit.
- PR #23 preserves Dimas's schema-v2 GTX 1080 observation: 18/18 measured
  requests valid, full GPU placement, frozen Ollama/model identity, and
  byte-exact raw artifacts. It remains outside the primary comparison.
- Completed milestones M0 Bootstrap and M1 Measured Pilot are closed. There
  are no open pull requests or obsolete remote development branches.

## In Progress

- The RTX 5060 host must replace its observed Ollama 0.34.4 with the frozen
  0.34.2 before launching its primary pilot.
- Quirence and Qcsteeven must independently run the tagged primary configs on
  RTX 5060 Laptop and RTX 4060 Ti respectively, then publish only validated
  raw artifacts through reviewed result PRs.
- All four benchmark model digests must be frozen before `benchmark-v1` is
  enabled on either primary host.

## Next Acceptance Gate

1. Check out the exact `pilot-v1-code` tag on each primary host.
2. Run `doctor` with the committed host config and confirm Ollama 0.34.2, the
   frozen digest, full GPU placement, and usable NVML energy telemetry.
3. Produce three independent 18-request launches per primary host without
   changing code, prompts, runtime, model digest, or validity policy.
4. Accept only runs with `validation.json: ok=true`; publish raw artifacts and
   the append-only log entry through a reviewed result PR.
5. Freeze all four benchmark model digests before enabling `benchmark-v1`.

## Open Research Work

- RTX 5060 and RTX 4060 Ti publishable pilots plus three independent
  calibration launches on each primary host.
- A corrected implementation of the rank-inversion analysis after clean,
  compatible campaign data exists. PR #18 is not the frozen implementation.
- External wattmeter validation remains outside MVP; all reported energy and
  cost values are GPU-only estimates.

## Latest Validated Run

The latest validated artifact is
`pilot-v1-observation-gtx1080-observation-20260928T155322Z-989238`: 18/18 valid
requests on GTX 1080. It is observation-only and cannot enter primary decision
blocks. No primary-host run has been published yet.
