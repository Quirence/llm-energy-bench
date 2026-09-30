# Paper Dataset Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the auditable two-host dataset and produce the preregistered repeatability, bootstrap, and rank-inversion verdict without changing the research hypothesis after observing the data.

**Architecture:** Keep raw run directories immutable. Add a focused `analysis.py` module that validates role-specific input runs, derives calibration thresholds, evaluates host-by-workload decision blocks, and writes deterministic study-level JSON/CSV/Markdown artifacts. Expose it through one explicit CLI command whose calibration and benchmark inputs cannot be silently mixed.

**Tech Stack:** Python 3.12 standard library, existing JSON/JSONL result contracts, `pytest`, `ruff`.

**Spec:** `docs/research-plan.md`

## Global Constraints

- Primary inference remains Ollama 0.34.2 at commit `d587a5d6fbeae039009a4e722f2af1249ebcbbf4` with the four frozen model digests.
- Primary decision blocks are `host × prompt category`; GTX 1080 remains observation-only.
- Quality eligibility is the preregistered inclusive floor `quality_score >= 0.75`, with equal prompt weighting.
- Calibration uses exactly three independent launches per primary GPU and run-level ratio-of-sums metrics.
- Material threshold is `max(5%, 3 × max(CV_speed, CV_energy))` per host and category.
- Bootstrap uses seed 42, 10,000 resamples, prompt IDs first and repetitions within prompts second.
- A material pairwise inversion conservatively requires both opposite metric effects to clear the threshold and both 95% confidence intervals to exclude zero.
- Energy claims remain GPU-only NVML estimates; no wall-energy or cluster TCO claim is permitted.

## Review Focus

- A valid-looking but incomplete or digest-mismatched benchmark run must fail instead of entering the verdict.
- Calibration host IDs may differ from benchmark host IDs; matching uses the hashed GPU fingerprint and rejects ambiguous mappings.
- Bootstrap must preserve prompt/repetition pairing between model configurations and must not average per-request ratios.
- A model below the quality floor on only one host must be excluded only on that host and reported explicitly.
- Observation-only runs must never increase the primary block denominator or change the hypothesis verdict.

---

### Task 1: Consolidate calibration evidence

**Files:**
- Add: six reviewed pilot run directories under `experiments/runs/`
- Modify: `docs/experiment-log.md`

**Interfaces:**
- Consumes: schema-v2 run artifacts from commits `1b74e4e` and `4e0a3c0`.
- Produces: exactly three validated calibration launches for each primary GPU fingerprint.

- [ ] Cherry-pick each contributor's calibration commit while preserving authorship and the append-only log.
- [ ] Regenerate each validation/report and verify no tracked bytes change.
- [ ] Verify 18/18 valid requests, identical pilot prompt hash, pinned Q4 digest, and no privacy findings.
- [ ] Commit each contributor's calibration evidence separately.

### Task 2: Statistical core

**Files:**
- Create: `src/llm_energy_bench/analysis.py`
- Create: `tests/test_analysis.py`

**Interfaces:**
- Consumes: tuples of calibration and benchmark run directories.
- Produces: `analyze_study(calibration_dirs, benchmark_dirs, *, seed=42, resamples=10000) -> StudyAnalysis`.

- [ ] Write failing tests for sample CV, the 5% floor, GPU-fingerprint mapping, strict run compatibility, equal-prompt quality, paired hierarchical bootstrap, host-local exclusion, all-pair inversion detection, and observation exclusion.
- [ ] Run focused tests and verify failures are caused by the missing module/API.
- [ ] Implement immutable analysis dataclasses, input validation, ratio-of-sums aggregation, calibration thresholds, and deterministic paired bootstrap.
- [ ] Run focused tests and the complete suite.
- [ ] Commit as `feat: add preregistered study analysis`.

### Task 3: CLI and deterministic study artifacts

**Files:**
- Modify: `src/llm_energy_bench/cli.py`
- Modify: `tests/test_cli.py`
- Extend: `tests/test_analysis.py`

**Interfaces:**
- Consumes: repeated `--calibration`, repeated `--benchmark`, and `--output-dir` arguments.
- Produces: `analysis.json`, `calibration.csv`, and `report.md` under the chosen study directory.

- [ ] Write failing parser/exit-code and byte-idempotence tests.
- [ ] Verify RED, then implement `analyze` without changing existing command behavior.
- [ ] Verify GREEN and run the complete suite.
- [ ] Commit as `feat: add frozen dataset analysis command`.

### Task 4: Freeze the study result and documentation

**Files:**
- Create: `experiments/studies/paper-dataset-v1/analysis.json`
- Create: `experiments/studies/paper-dataset-v1/calibration.csv`
- Create: `experiments/studies/paper-dataset-v1/report.md`
- Modify: `STATUS.md`
- Modify: `docs/experiment-log.md`
- Modify: `docs/paper-draft.md`
- Modify: `docs/project-state-for-owner.md`

**Interfaces:**
- Consumes: the two accepted primary campaigns and six calibration launches.
- Produces: the frozen two-host verdict and source numbers for the article draft.

- [ ] Run `analyze` twice and require byte-identical study artifacts.
- [ ] Record calibration CVs, thresholds, quality exclusions, block agreement, inversion results, limitations, and exact input run IDs.
- [ ] Update documentation without rewriting historical log entries.
- [ ] Commit as `data: freeze paper dataset v1`.

### Task 5: Final verification and publication

**Files:**
- Verify the complete branch.

**Interfaces:**
- Consumes: all prior task commits.
- Produces: one reviewable finalization PR against `main`.

- [ ] Run `ruff check`, `ruff format --check`, all tests, deterministic analysis regeneration, privacy scan, and `git diff --check`.
- [ ] Perform an independent whole-branch review and fix every Critical/Important finding via RED→GREEN tests.
- [ ] Push `analysis/freeze-paper-dataset`, create one PR, request Qcsteeven and Skipl1 review, and leave `main` protected until approval.
