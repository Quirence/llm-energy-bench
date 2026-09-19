# Project Status

Last updated: 2026-09-19

## Current Milestone

M1 — Measured Pilot. Tasks 1–7 are implemented; Task 8 remains.

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
- Task 7: read-only environment diagnosis, CLI execution path, validation
  summaries, aggregate CSV/Markdown reports, quality floor, and speed/energy
  ranking comparison.
- Integrated test baseline: 219 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.

## In Progress

- Task 8: validate the complete path with a real NVIDIA GPU and Ollama model.

## Next

- Task 8: RTX 3050 hardware pilot.
- Task 9: freeze the two-host benchmark-v1 prompt set and model matrix.

## Blockers

- No known software blocker.
- Hardware validation is still pending: NVML is covered by a fake binding and
  Ollama by mock HTTP streams, but neither path has been validated on a real
  GPU in this repository yet.
- Ruff is enforced in CI but is not installed in the current global Python
  environment; the local compile and pytest checks pass.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run.
