# Project Status

Last updated: 2026-09-25

## Current Milestone

M1 — Measured Pilot. Tasks 1–7 and Task 9 are implemented; Task 8 remains.

## Done

- Research question and failure condition documented.
- MVP architecture and data flow approved.
- Initial model and quantization matrix fixed.
- Parallel implementation from Qcsteeven and Dimas reviewed and integrated
  into `main` while preserving both contributors' commits.
- CODEOWNERS plus reproducible bug, experiment, and pull-request templates
  enforce the two-author review workflow in the repository.
- The versioned collaboration guide maps `@Qcsteeven` to NVML/RTX 4060 work
  and `@Skipl1` (Dimas) to the Ollama runtime boundary and Issue #7.
- Public GitHub milestones `M0 Bootstrap`, `M1 Measured Pilot`, `M2 Two-GPU
  Study`, and `M3 Paper Dataset` track the delivery stages.
- `main` requires a pull request, one approval, CODEOWNERS review, successful
  Windows and Linux CI, resolved conversations, and linear history. Force
  pushes and branch deletion are disabled, including for administrators.
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
- Issue #7 (Dimas): the Ollama runtime path is validated against a live
  Ollama 0.34.2 server. `doctor` reports the real version, digest and
  full-VRAM placement, and a streaming request completes end to end. The
  observation is recorded in `docs/ollama-runtime-observations.md`.
- Integrated test baseline: 244 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.
- A provisional local integration of PRs #14--#16 passes all 254 tests plus
  `ruff check`, and completed the six-prompt RTX 5060 acceptance workload with
  18/18 measured requests semantically valid. Its artifacts remain ignored
  until the reviewed fixes are merged and the frozen run is repeated.

## In Progress

- Task 8: repeat the complete RTX 5060 path from a reviewed, merged commit and
  publish only that reproducible run.
- PR #14 enforces explicit full-GPU placement, PR #15 hardens NVML energy
  fallback, and PR #16 implements the reviewed template-cache baseline rule.
- Monitoring the state-dependent total-energy counter through explicit source
  recording; no further telemetry policy change is proposed before review of
  the provisional evidence.

## Next

- Review and merge PRs #14–#16, then execute the 18-request `pilot-v1` on the
  RTX 5060 Laptop and commit it only if semantic validation passes.

## Blockers

- The validity fixes are green in CI but still await the required collaborator
  reviews and integration. Running and publishing the pilot against only a
  subset of those fixes would knowingly produce incomparable artifacts.
- The raw SHA-256 cache-buster in PR #16 reproducibly changes the arithmetic
  utility prompt into a safety refusal on the pilot model. A deterministic
  UUID-form first-line marker preserved the answer and the 20-token template
  floor in 10/10 diagnostic requests; that reviewed change is now a prerequisite
  for repeating the pilot.
- Publishable end-to-end experimental validation is still pending. A local
  combined acceptance run completed with 18/18 valid measured requests, but
  the three prerequisite fixes remain unmerged; therefore those artifacts are
  deliberately excluded from the research dataset.
- Real NVML probing succeeds on the RTX 3050 and exposes all requested fields.
  Driver 572.83 reports an inconsistent total-energy counter, so the new
  per-request sanity check correctly falls back to instantaneous power
  integration; this still needs validation under model load.
- RTX 5060 Laptop driver 591.66 exposes a state-dependent total-energy
  counter: it can be physically inconsistent at idle or return no positive
  request delta, while most inference intervals agree reasonably with power
  integration. The per-request sanity gate and explicit fallback are therefore
  still required. External-meter validation remains out of MVP scope.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run. The GTX 1080
observation of 2026-09-20 exercised the runtime path end to end, but it used a
non-matrix GPU and three prompts instead of the frozen protocol, and all three
of its requests were rejected by the cached-token rule. It is an observation,
not a run.
