# Project Status

Last updated: 2026-09-19

## Current Milestone

M1 — Measured Pilot. Tasks 1–6 are implemented; Tasks 7–8 remain.

## Done

- Research question and failure condition documented.
- MVP architecture and data flow approved.
- Initial model and quantization matrix fixed.
- Parallel implementation from Qcsteeven and Dimas reviewed and integrated
  into `main` while preserving both contributors' commits.
- Detailed implementation plan prepared.
- Task 1 (Qcsteeven): package shell, `doctor`/`run`/`report` parsing, fixed
  exit codes, packaging, and Windows/Linux CI.
- Task 2 (Qcsteeven): strict experiment config and prompt-set contracts plus
  the six-prompt RTX 3050 pilot inputs.
- Task 3 (Qcsteeven): atomic raw-result writers, gzip telemetry, checksums,
  privacy guards, run directories, and basic validation.
- Task 4 (Dimas): read-only Ollama inventory/preload and streaming inference
  measurements, including TTFT, placement, digests, and partial failures.
- Task 5 (Qcsteeven): NVML capability probe and request-scoped telemetry
  sampler with total-energy/instant-power/legacy-power fallback.
- Task 6: deterministic warm experiment runner, cache contamination handling,
  request metrics, partial-run preservation, and semantic validation.
- Integrated test baseline: 207 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.

## In Progress

- Task 7: wire `doctor`, `run`, and `report` into the CLI and implement
  aggregate CSV/Markdown reporting.

## Next

- Task 7: doctor output and reports.
- Task 8: RTX 3050 hardware pilot.

## Blockers

- No known software blocker.
- Hardware validation is still pending: NVML is covered by a fake binding and
  Ollama by mock HTTP streams, but neither path has been validated on a real
  GPU in this repository yet.
- The runner is implemented but not exposed through the CLI yet. `doctor`,
  `run`, and `report` intentionally return exit code 3 until Task 7.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run.
