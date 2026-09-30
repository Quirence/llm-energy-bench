# Project Status

Last updated: 2026-09-30

## Current Milestone

M3 — Paper Dataset. The two-primary-GPU dataset and its preregistered analysis
are complete. The branch `analysis/freeze-paper-dataset` is awaiting review
before merge and tagging.

## Done

- Python 3.12 CLI commands `doctor`, `run`, `report`, and `analyze` are covered
  by Windows/Linux hardware-independent tests.
- Ollama streaming, TTFT, full-GPU placement, schema-v2 cache/load controls,
  request-scoped NVML telemetry, atomic artifacts, validation, privacy guards,
  and deterministic reports are implemented.
- Runtime Ollama 0.34.2, the four model digests, prompt set, inference controls,
  and `benchmark-v1-code-v5` commit are frozen.
- Three independent `pilot-v1` calibration launches are accepted on each
  primary GPU: RTX 5060 Laptop and RTX 4060 Ti desktop (108/108 valid requests).
- The compatible primary campaigns contain 480/480 valid requests on each GPU.
  Their logical prompt maps, runtime, code commit, and model digests match.
- The GTX 1080 campaign is retained as observation-only evidence and cannot
  enter the primary hypothesis verdict.
- `analyze` validates role-specific inputs, requires exactly three calibration
  launches per primary GPU, applies equal-prompt quality weighting, computes
  ratio-of-sums metrics, and evaluates all pairwise rank inversions.
- Study artifacts are frozen under `experiments/studies/paper-dataset-v1/` and
  regenerate byte-identically.

## Frozen Result

- Speed and GPU-energy winners agree in 6/6 primary `host × workload` blocks.
- Llama 3.2 Q4 is the top eligible configuration in every primary block.
- No descriptive or material pairwise speed/energy rank inversion is present.
- The preregistered rank-inversion hypothesis is therefore **not supported in
  the investigated domain**. This is not a universal equivalence claim.
- Llama 3.2 Q8 is quality-eligible on RTX 5060 (0.750) but excluded locally on
  RTX 4060 Ti (0.725); the other three configurations are eligible on both.
- Repeatability-based material thresholds range from 5.00% to 63.14%, with the
  largest value in the very short scored block on RTX 4060 Ti.

## Remaining Before Article Drafting

1. Obtain independent review from Qcsteeven and Skipl1.
2. Merge the finalization PR and tag the merge commit `paper-dataset-v1`.
3. Treat `experiments/studies/paper-dataset-v1/analysis.json` as the numeric
   source of truth while writing the article.
4. Select the target journal and adapt formatting and bibliography.
5. If stronger energy claims are desired, run a separate wall-meter validation;
   current conclusions are GPU-only NVML conclusions.

## Latest Validated Evidence

- RTX 5060: `benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3`.
- RTX 4060 Ti: `benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c`.
- Study report: `experiments/studies/paper-dataset-v1/report.md`.
