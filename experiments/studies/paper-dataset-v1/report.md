# Frozen paper dataset v1

## Primary result

- Hypothesis outcome: `not_supported`.
- Speed and energy winners agree in 6/6 host × workload blocks (100.0%).
- Material pairwise rank inversions: 0.
- Quality floor: 75%, inclusive.
- Bootstrap: 10,000 hierarchical paired resamples, seed 42.

Within the frozen two-GPU domain, the energy-aware ranking did not change the top engineering choice relative to speed-only ranking. This does not support the rank-inversion hypothesis in the investigated domain.

## Primary benchmark inputs

- `benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3`
- `benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c`

## Calibration inputs

- `pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749`
- `pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922`
- `pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6`
- `pilot-v1-rtx4060ti-desktop-20260929T002903Z-552fa9`
- `pilot-v1-rtx4060ti-desktop-20260929T003009Z-f4bcf0`
- `pilot-v1-rtx4060ti-desktop-20260929T003046Z-9daa3d`

## Repeatability thresholds

| Host | Workload | Speed CV | Energy CV | Material threshold |
|---|---:|---:|---:|---:|
| maibenben-x16c | long | 1.57% | 2.99% | 8.97% |
| maibenben-x16c | scored | 7.72% | 6.03% | 23.16% |
| maibenben-x16c | short | 0.35% | 4.77% | 14.32% |
| rtx4060ti-desktop | long | 0.32% | 4.16% | 12.47% |
| rtx4060ti-desktop | scored | 5.95% | 21.05% | 63.14% |
| rtx4060ti-desktop | short | 0.40% | 0.86% | 5.00% |

The threshold is `max(5%, 3 × max(CV_speed, CV_energy))` for each host and workload category.

## Decision blocks

| Host | Workload | Speed winner | Energy winner | Agree | Eligible models |
|---|---:|---|---|---:|---:|
| maibenben-x16c | long | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 4 |
| maibenben-x16c | scored | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 4 |
| maibenben-x16c | short | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 4 |
| rtx4060ti-desktop | long | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 3 |
| rtx4060ti-desktop | scored | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 3 |
| rtx4060ti-desktop | short | llama3.2:3b-instruct-q4_K_M | llama3.2:3b-instruct-q4_K_M | yes | 3 |

## Quality eligibility

- `llama3.2:3b-instruct-q8_0` on `rtx4060ti-desktop` was excluded: score 0.725 is below the inclusive 0.750 floor.

## Pairwise rank inversions

- No descriptive pairwise speed/energy rank inversions were found.

## Limitations

- Energy is GPU-only NVML telemetry, not wall-system energy.
- The primary domain contains two NVIDIA GPUs, one runtime, and four model/quantization configurations.
- Quality eligibility is host-local because deterministic settings did not guarantee byte-identical output across GPUs.
- Absence of a material inversion in this domain is not evidence that no inversion exists elsewhere.

All throughput and efficiency values use ratio-of-sums. Scored-prompt quality is averaged within prompt before prompts receive equal weight.
