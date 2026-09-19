# Project Status

Last updated: 2026-09-19

## Current Milestone

M1 — Measured Pilot. Tasks 1–5 are integrated; Tasks 6–8 remain.

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
- Integrated test baseline: 189 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.

## In Progress

- No unfinished implementation is present on `main`. The next code change is
  Task 6, which will connect the independently tested contracts.

## Next

- Task 6: metrics and experiment runner, wiring the Ollama client to the NVML
  sampler.
- Task 7: doctor output and reports.
- Task 8: RTX 3050 hardware pilot.

## Blockers

- No known software blocker.
- Hardware validation is still pending: NVML is covered by a fake binding and
  Ollama by mock HTTP streams, but neither path has been validated on a real
  GPU in this repository yet.
- The CLI is a command shell only. `doctor`, `run`, and `report` intentionally
  return exit code 3 until Tasks 6 and 7 wire in their implementations.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run.
