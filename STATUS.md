# Project Status

Last updated: 2026-09-20

## Current Milestone

M1 — MVP implementation. Software complete; hardware validation pending.

## Done

- Research question, failure condition, and analysis rules documented.
- MVP architecture and data flow approved.
- Task 1: package shell, command parsing, fixed exit codes, Windows/Linux CI.
- Task 2: experiment and prompt contracts, pilot config, six pilot prompts.
- Task 3: immutable run artifacts, integrity checks, privacy rules.
- Task 4: Ollama streaming client with client-side timing.
- Task 5: NVML capability probe and telemetry sampler.
- Task 6: preflight, measured execution, and derived request metrics.
- Task 7: environment doctor, summary CSV, and Markdown reports.

## In Progress

- Review and merge of the seven feature branches.

## Next

- Task 8: RTX 3050 pilot on a Windows host — the first run on real hardware.
- Task 9: two-host benchmark protocol (benchmark-v1).

## Blockers

- No measurement has touched real hardware yet. Every module is verified
  against fakes only, because the development WSL host exposes no NVIDIA
  driver: `probe` there correctly reports `NvmlUnavailable`, and `doctor`
  correctly exits 3. Task 8 on Windows is what turns this from plausible
  software into a validated instrument.

## Latest Validated Run

None. Task 8 is the first measured run.
