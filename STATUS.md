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
- `uuid_slot_prefix_v3` passed a Qwen-specific 18/18 hardware acceptance with
  the expected three-token floor and zero excess cached tokens.
- The RTX 5060 `benchmark-v1` campaign completed with 480/480 valid measured
  requests and `validation.ok=true` from tag `benchmark-v1-code-v3`.
- Derived validation is idempotent: `validation.json` does not recursively hash
  itself, and repeated report generation leaves its bytes unchanged.

## In Progress

- The first RTX 5060 `benchmark-v1` attempt completed 480/480 requests but is
  excluded because two Qwen requests exceeded the registered cache-boundary
  allowance. The complete diagnostic run is preserved in `experiments/runs/`.
- `uuid_slot_prefix_v2` passed a Llama acceptance but inflated Qwen's warm-up
  floor because sequential slots `00` through `03` share one leading
  character. The partial follow-up run is excluded.
- The accepted RTX 5060 aggregate speed and energy rankings agree in all three
  workload categories. This is a single-host observation, not the final
  hypothesis decision.
- The RTX 4060 Ti pilot result branch exists and requires review; its complete
  benchmark must use the same v3 tag before a two-host comparison is valid.

## Next Acceptance Gate

1. Review and publish the v3 fix, acceptance artifacts, and accepted RTX 5060
   campaign without changing the frozen commit.
2. Have the RTX 4060 Ti contributor pull the same tag, confirm the four pinned
   digests, and execute the committed companion config without code changes.
3. Accept only `validation.json: ok=true` with all 480 requests valid.
4. Implement the preregistered bootstrap/material-effect analysis against the
   two compatible primary runs.
5. Compare only those complete compatible runs in the paper tables.

## Open Research Work

- RTX 5060 and RTX 4060 Ti publishable pilots plus three independent
  calibration launches on each primary host.
- A corrected implementation of the rank-inversion analysis after clean,
  compatible campaign data exists. PR #18 is not the frozen implementation.
- External wattmeter validation remains outside MVP; all reported energy and
  cost values are GPU-only estimates.

## Latest Validated Run

The latest validated artifact is
`benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1`: 480/480 valid measured
requests on RTX 5060 from `benchmark-v1-code-v3`. Its observed aggregate speed
and energy rankings agree in 3/3 workload blocks. The result remains
single-host; there is still no compatible two-host research dataset.
