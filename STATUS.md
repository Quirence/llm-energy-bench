# Project Status

Last updated: 2026-09-19

## Current Milestone

M1 — Measured Pilot. Tasks 1–7 and Task 9 are implemented; Task 8 remains.

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
- Task 9: frozen four-configuration `benchmark-v1` matrix, 24-prompt workload,
  repeatability CV, bootstrap materiality rule, and explicit negative-result
  decision criterion.
- Integrated test baseline: 222 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.

## In Progress

- Task 8: validate the complete path with a real NVIDIA GPU and Ollama model.

## Next

- Task 8: RTX 3050 hardware pilot.

## Blockers

- No known software blocker.
- Hardware validation is still pending: NVML is covered by a fake binding and
  Ollama by mock HTTP streams, but neither path has been validated on a real
  GPU in this repository yet.
- The official Ollama 0.34.2 installer download timed out repeatedly from
  GitHub on this host. No package was installed; retrying the download is the
  current external blocker for Task 8.
- Ruff is enforced in CI but is not installed in the current global Python
  environment; the local compile and pytest checks pass.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run.
