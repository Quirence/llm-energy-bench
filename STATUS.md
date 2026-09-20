# Project Status

Last updated: 2026-09-20

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
- Integrated test baseline: 239 tests pass on Python 3.12 without Ollama or
  NVIDIA hardware.

## In Progress

- Task 8: validate the complete path with a real NVIDIA GPU and Ollama model.
- Agreeing the prompt-cache validity rule the Issue #7 observation makes
  necessary.

## Next

- Decide the cached-token rule and the cache-buster shape, then Task 8:
  RTX 3050 hardware pilot.

## Blockers

- **Every measured request is currently invalid.** Ollama reuses the chat
  template preamble, so `prompt_eval_cached_count` never drops below about 20
  tokens after the first request, while `runner.py` and `results.py` invalidate
  any request with a non-zero cached count. Measured on a live 0.34.2 server;
  the floor is constant across prompt bodies and lengths. A pilot cannot
  produce valid data until the rule distinguishes the template floor from real
  contamination.
- **The cache buster leaks a shared prefix.** Request IDs share a long
  run-specific head that Ollama caches: 46 of 69 prompt tokens came from cache
  on a short prompt, so prefill was measured on a fraction of the prompt. The
  per-request entropy has to come first.
- Both are documented with evidence and a proposed fix in
  `docs/ollama-runtime-observations.md` and await review by the owners of
  `runner.py` and `results.py`.
- End-to-end hardware validation on a matrix GPU is still pending. The Ollama
  runtime path itself is now validated on real hardware, but only on a GTX
  1080 observation host that is outside the research matrix.
- The official Ollama 0.34.2 installer download timed out repeatedly from
  GitHub on the RTX 3050 host. It installed without trouble on the GTX 1080
  observation host, so the download, not the package, is the obstacle there.
- Real NVML probing succeeds on the RTX 3050 and exposes all requested fields.
  Driver 572.83 reports an inconsistent total-energy counter, so the new
  per-request sanity check correctly falls back to instantaneous power
  integration; this still needs validation under model load.

## Latest Validated Run

No experimental runs yet. Task 8 is the first measured run. The GTX 1080
observation of 2026-09-20 exercised the runtime path end to end, but it used a
non-matrix GPU and three prompts instead of the frozen protocol, and all three
of its requests were rejected by the cached-token rule. It is an observation,
not a run.
