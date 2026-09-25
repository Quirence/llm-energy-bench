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
- `main` requires a pull request, one approval, successful Windows and Linux
  CI, resolved conversations, and linear history. The cross-review CODEOWNERS
  map is included in the stabilization branch; code-owner enforcement can be
  enabled after that branch merges without creating an ownership deadlock.
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
- The consolidated stabilization branch passes 258 tests plus `ruff check` and
  `ruff format --check` on Python 3.12 without requiring NVIDIA hardware.
- Its local RTX 5060 acceptance check completed with 18/18 valid measured
  requests, cache baseline 20, excess cache 0, and quality score 1.0. The raw
  artifact remains unpublished until the reviewed branch is merged and tagged.

## In Progress

- Review the single stabilization pull request that supersedes PRs #9, #12,
  and #14--#16. Its code combines doctor path resolution, cross-review owners,
  full-GPU placement, NVML sanity checks, the template floor and the verified
  UUID cache marker.

## Next

- Merge the stabilization pull request, tag its merge commit `pilot-v1-code`,
  and run the committed RTX 5060 and RTX 4060 host configs independently.

## Blockers

- The stabilization branch still needs one collaborator approval and green
  Windows/Linux CI before it can become the tagged baseline.
- Publishable end-to-end experimental validation remains pending. The local
  acceptance run validates the implementation, but comparable artifacts must
  come from the reviewed tag on both primary hosts.
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

No publishable experimental runs yet. The latest local acceptance check is the
RTX 5060 18-request stabilization run documented in the experiment log; it is
valid as implementation evidence but intentionally excluded from the dataset
because its branch has not been reviewed, merged, and tagged.
