# llm-energy-bench

Research tool for measuring local LLM inference performance, GPU energy use, and approximate cost.

The project starts as a small experimental bench, not as a production monitoring platform. Its first goal is to check whether energy-aware metrics change the engineering choice of local LLM configuration compared with speed-only benchmarks.

## Initial Research Question

Does the preferred local LLM configuration change when comparing models, quantization modes, context lengths, and GPUs by:

- latency;
- tokens per second;
- GPU energy per request;
- tokens per joule;
- approximate cost per 1M tokens?

## Minimal Scope

- Run fixed prompt sets against local inference runtimes.
- Collect runtime metrics such as latency and token counts.
- Sample NVIDIA GPU telemetry through NVML.
- Save raw runs and derived metrics.
- Generate simple tables and plots for comparison.

## Non-Goals

- Datacenter orchestration.
- Production monitoring.
- Automatic optimization claims without experiments.
- Universal conclusions about all LLM deployments.

## Planned Structure

- `src/llm_energy_bench/` - tool source code.
- `prompts/` - prompt sets for repeatable experiments.
- `experiments/` - local experiment outputs, configs, and notes.
- `notebooks/` - analysis notebooks.
- `docs/` - research notes and methodology drafts.

## Project Documents

- [Current project status](STATUS.md)
- [Approved MVP design](docs/superpowers/specs/2026-09-19-llm-energy-bench-design.md)
- [MVP implementation plan](docs/superpowers/plans/2026-09-19-llm-energy-bench-mvp.md)
- [Initial research plan](docs/research-plan.md)

Implementation has not started yet. The approved design and implementation
plan are committed first so both authors can review the same contracts before
working in parallel.
