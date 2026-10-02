# Project Status

Last updated: 2026-10-02

## Current Milestone

M4 — Power Quality Study. Первый набор данных и его вывод остаются
зафиксированными. Реализуется отдельный эксперимент по кривым
`power limit → скорость/энергия/точность`; производственные измерения ещё не
начаты.

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
- Добавлен строгий контракт `power-quality-v2`: schema v3, точные ответы,
  expected power limit, профиль min/default/max/current, проверка пустого
  Ollama и фонового состояния GPU до загрузки модели.
- Отдельная команда `analyze-power-quality` проверяет полную матрицу,
  совместимость runtime/prompts/digest/controls, отношения сумм, энергию и
  задержку на правильный ответ и границу компромисса. GTX 1080 остаётся
  внешним наблюдением.
- Заморожен набор из 12 запросов и 24 конфигурации-кандидата RTX 5060 для
  уровней 80/65/50/35 Вт. Подтверждён `doctor` при 80 Вт на Ollama 0.35.0.

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

## Remaining Before Power-Quality Measurements

1. Из административной PowerShell подтвердить установку 65/50/35 Вт на RTX
   5060 и выполнить локальную аппаратную приёмку; обычная PowerShell получила
   `Insufficient Permissions`.
2. Получить от Льва профиль RTX 4060 Ti, а от Димы профиль GTX 1080; после
   этого центрально зафиксировать их TOML и дополнить runbook.
3. Один раз выполнить полный pytest/ruff gate, интегрировать ветку и выпустить
   метку `power-quality-v2-code`.
4. После метки собрать 24 + 24 + 18 запусков и построить отдельный отчёт. Не
   изменять `paper-dataset-v1` и не смешивать external GPU с primary.

## Latest Validated Evidence

- RTX 5060: `benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3`.
- RTX 4060 Ti: `benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c`.
- Study report: `experiments/studies/paper-dataset-v1/report.md`.
- Power-quality profile: RTX 5060 Laptop, driver 591.66, current 80 Вт,
  default 50 Вт, range 5–115 Вт; Ollama 0.35.0; Q4 Llama digest и полное
  размещение подтверждены. Производственных schema-v3 runs пока нет.
