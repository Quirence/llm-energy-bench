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

If energy-aware ranking almost always matches speed-only ranking, the project should be reframed or dropped as a diploma topic.
