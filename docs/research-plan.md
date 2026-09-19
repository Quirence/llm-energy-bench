# Research Plan

## Hypothesis

Energy-aware metrics may change the ranking of local LLM configurations compared with speed-only metrics.

## Experimental Campaign

The campaign is staged so hardware and telemetry problems are found before the
research comparison begins.

### Pilot

- GPU: RTX 3050 Laptop, used only as a smoke/pilot host;
- runtime: Ollama;
- model: `llama3.2:3b-instruct-q4_K_M`;
- prompts: two short/decode, two long/prefill, and two scored utility prompts;
- two excluded warm-up requests and three measured repetitions;
- 18 measured requests in total.

### Main Matrix

- GPUs: MAIBENBEN X16C RTX 5060 Laptop and RTX 4060 desktop;
- runtime: Ollama, with one pinned version for the campaign;
- models/quantizations:
  - `qwen3:4b-instruct-2507-q4_K_M`;
  - `qwen3:4b-instruct-2507-q8_0`;
  - `llama3.2:3b-instruct-q4_K_M`;
  - `llama3.2:3b-instruct-q8_0`;
- fixed inference settings: context length 4096, temperature 0, seed 42,
  concurrency 1, and f16 KV cache;
- `benchmark-v1`: 24 prompts and five measured repetitions per configuration.

Model tags and digests must be checked before the campaign. A run records the
actual Ollama digest, runtime and driver versions, prompt/config hashes, power
limit, temperature, VRAM context, and the telemetry source used.

The four tags were rechecked against the official
[Qwen3](https://ollama.com/library/qwen3/tags) and
[Llama 3.2](https://ollama.com/library/llama3.2/tags) registries on
2026-09-19. Tags are configuration names, not immutable identities, so this
check does not replace the digest captured by each run. The checked-in
`benchmark-v1.toml` is the MAIBENBEN copy; the RTX 4060 copy changes only
`host_id`, while prompt, runtime, model, GPU-sampling, and inference controls
remain byte-for-byte equivalent.

## Core Metrics

- latency;
- time to first token (TTFT), when the runtime exposes a meaningful stream;
- prompt tokens;
- output tokens;
- prefill, decode, and end-to-end tokens per second;
- average GPU power;
- observed peak GPU power;
- GPU energy per request;
- joules per output token;
- tokens per joule;
- optional GPU-only electricity cost per 1M output tokens when an explicit
  tariff and currency are supplied.

## Controls

- fixed runtime version;
- fixed driver version;
- fixed model files;
- fixed prompt set;
- warm-up runs;
- AC power for laptops;
- record GPU temperature and power limits where possible.

NVML is the MVP measurement source. A hardware total-energy counter is
preferred; otherwise the tool integrates instantaneous power, then legacy
power. These figures describe GPU-only energy, not wall-system energy. An
external wattmeter is reserved for a later validation study and is required
before making whole-system energy or cost claims.

## Main Failure Condition

### Repeatability and material effects

Before the main campaign, each host performs three independently launched
calibration runs using the same Q4 model and prompt subset. For each workload
category, repeatability CV is the sample standard deviation divided by the
mean of the run-level aggregate metric. The material-effect threshold is
`max(5%, 3 × max(CV_speed, CV_energy))` for that host and workload category.

Main comparisons use ratios of sums for throughput and energy efficiency.
Scored prompts are averaged first over repetitions of one prompt and then over
prompt IDs; configurations below 75% quality are excluded from ranking. A
deterministic bootstrap with seed 42 and 10,000 resamples samples prompt IDs,
then repetitions within each selected prompt. A speed/energy rank inversion
is material only when the metrics prefer different configurations, the
relative pairwise effect reaches the threshold, and its bootstrap 95%
confidence interval does not cross zero. The first report implementation
shows descriptive ranks only; statistical materiality is evaluated after the
calibration data exists.

The decision blocks are `host × prompt category`. If speed and energy select
the same top eligible configuration in at least 90% of blocks and no material
inversion exists, the hypothesis is reported as unsupported in the tested
scope. In that case the diploma topic must be narrowed, reframed around the
measurement method, or abandoned rather than rescued with a post-hoc claim.

### Prompt-set limits

`benchmark-v1` contains eight decode-oriented short prompts, eight
prefill-oriented long prompts, and eight deterministic utility checks. The
quality score is deliberately simple substring matching, so scored prompts
request exact short answers to reduce ambiguity. It is a guard against gross
quality loss, not a general model-quality benchmark.
