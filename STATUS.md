# Project Status

Last updated: 2026-09-29

## Current Milestone

M2 — Two-GPU Study. The reviewed pilot baseline is tagged `pilot-v1-code`;
the four-configuration benchmark is in hardware acceptance and no publishable
two-host dataset exists yet.

## Done

- The Python 3.12 CLI implements `doctor`, `run`, and `report` with stable exit
  codes and more than 300 Windows/Linux hardware-independent tests.
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
- Completed milestones M0 Bootstrap and M1 Measured Pilot are closed.
- Three complete RTX 5060 pilot repeatability launches passed validation with
  54/54 measured requests. They support instrument repeatability only and are
  not a two-host research result.
- All four `benchmark-v1` model tags and exact digests are frozen for Ollama
  0.34.2 in the two primary-host configs.

## In Progress

- The first RTX 5060 `benchmark-v1` attempt completed 480/480 requests but is
  excluded because two Qwen requests exceeded the registered cache-boundary
  allowance. The complete diagnostic run is preserved in `experiments/runs/`.
- `uuid_slot_prefix_v2` is under acceptance. It assigns every warm-up and
  measured logical request a unique first UUID byte, eliminating the observed
  two-character marker-prefix collision without weakening the cache rule.
- The correction passed the full synthetic suite and an 18/18 RTX 5060
  hardware acceptance. It still needs a frozen tag after review and a clean
  480-request rerun.

## Next Acceptance Gate

1. Freeze and tag the corrected benchmark commit after collaborator review.
2. Repeat the full 480-request RTX 5060 campaign; accept only
   `validation.json: ok=true` with all 480 requests valid.
3. Have the RTX 4060 Ti contributor pull the same tag, confirm the four pinned
   digests, and execute the committed companion config without code changes.
4. Compare only the two complete compatible runs in the primary report.

## Open Research Work

- RTX 5060 and RTX 4060 Ti publishable pilots plus three independent
  calibration launches on each primary host.
- A corrected implementation of the rank-inversion analysis after clean,
  compatible campaign data exists. PR #18 is not the frozen implementation.
- External wattmeter validation remains outside MVP; all reported energy and
  cost values are GPU-only estimates.

## Latest Validated Run

The latest local validated artifact is
`pilot-v1-maibenben-x16c-rtx5060-20260929T012225Z-8f048a`: 18/18 valid requests
under `uuid_slot_prefix_v2`. It is a marker-policy acceptance run, not the
research campaign. The earlier 480-request benchmark attempt is deliberately
invalid and contributes no aggregates or rankings; there is still no
compatible two-host research dataset.
