# Project Status

Last updated: 2026-09-19

## Current Milestone

M1 — MVP implementation.

## Done

- Research question and failure condition documented.
- MVP architecture and data flow approved.
- Initial model and quantization matrix fixed.
- Collaboration workflow agreed for Quirence and Qcsteeven.
- Detailed implementation plan prepared.
- Task 1: package shell, `doctor`/`run`/`report` command parsing, fixed exit
  codes, and Windows/Linux CI.
- Task 5 (Qcsteeven): NVML capability probe and request-scoped telemetry
  sampler, covered by a fake NVML binding.

## In Progress

- Tasks 2, 3, 4 (Quirence): config and prompt contracts, result storage, and
  the Ollama streaming client.

## Next

- Task 6: metrics and experiment runner, wiring the Ollama client to the NVML
  sampler.
- Task 7: doctor output and reports.
- Task 8: RTX 3050 hardware pilot.

## Blockers

- The NVML sampler has no hardware validation yet. It is verified only against
  the fake binding; the development WSL host exposes no NVIDIA driver, so
  `probe` there correctly reports `NvmlUnavailable`. First real telemetry comes
  with the Task 8 pilot on Windows.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run.
