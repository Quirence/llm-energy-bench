# Research Plan

## Hypothesis

Energy-aware metrics may change the ranking of local LLM configurations compared with speed-only metrics.

## First Experiment

Start with a small matrix:

- 1-2 GPUs;
- 1 inference runtime;
- 2 models;
- 2 quantization modes, if available;
- 2 context lengths;
- 20-50 prompts;
- 3 repetitions per configuration.

## Core Metrics

- latency;
- prompt tokens;
- output tokens;
- tokens per second;
- average GPU power;
- peak GPU power;
- GPU energy per request;
- tokens per joule.

## Controls

- fixed runtime version;
- fixed driver version;
- fixed model files;
- fixed prompt set;
- warm-up runs;
- AC power for laptops;
- record GPU temperature and power limits where possible.

## Main Failure Condition

If energy-aware ranking almost always matches speed-only ranking, the project should be reframed or dropped as a diploma topic.
