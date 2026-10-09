# Project Status

Last updated: 2026-10-09

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
- Заморожен набор из 12 запросов и 12 конфигураций RTX 5060: две модели ×
  режимы Gaming 80 Вт и Turbo 115 Вт × три независимых запуска.
- Аппаратно подтверждено, что `nvidia-smi -pl` на MAIBENBEN не меняет лимит,
  а Gaming/Turbo дают NVML current/requested 80/115 Вт. Custom и Office
  исключены, поскольку отключают дискретную GPU.

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

## Remaining Before Multi-GPU Power-Quality Measurements

1. По опубликованной метке `power-quality-v2-profile` получить от Льва
   профиль RTX 4060 Ti, а от Димы профиль GTX 1080; после
   этого центрально зафиксировать их TOML и дополнить runbook.
2. Один раз выполнить полный pytest/ruff gate, интегрировать ветку и выпустить
   метку `power-quality-v2-code`.
3. После метки собрать 24 + 18 внешних запусков и построить общий отчёт. Не
   изменять `paper-dataset-v1` и не смешивать external GPU с primary.

## Latest Validated Evidence

- RTX 5060: `benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3`.
- RTX 4060 Ti: `benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c`.
- Study report: `experiments/studies/paper-dataset-v1/report.md`.
- Power-quality profile: RTX 5060 Laptop, driver 591.66, current 80 Вт,
  default 50 Вт, range 5–115 Вт; Ollama 0.35.0; Q4 Llama digest и полное
  размещение подтверждены. Четыре schema-v3 acceptance runs при 80 Вт имеют
  48/48 valid requests и чистую validation; отдельный mismatched run корректно
  отказал до первого запроса.
- Первая производственная половина RTX 5060 завершена в Gaming 80 Вт: шесть
  runs, 360/360 valid requests, максимальный telemetry gap 141 мс, CV tok/s
  0.72–3.03%, CV tok/J 1.27–6.92%. Целого run-выброса нет; технический отчёт
  воспроизводится побайтно. Для коротких exact-запросов энергия трактуется
  только агрегированно из-за 2–3 telemetry samples и fallback источника.
- Локальная матрица RTX 5060 завершена: 12 runs и 720/720 valid requests.
  Переход Turbo 115 Вт → Gaming 80 Вт уменьшил скорость на 4.87–6.51%,
  энергию запроса на 7.88–22.86% и повысил tok/J на 8.55–29.63%; exact
  quality не изменилась. По консервативному порогу эффект устойчив в 4/6
  workload-блоков, а long-блоки остаются неопределёнными. Это локальный
  результат двух режимов ноутбука, а не итог multi-GPU исследования.
- Ветка `feat/power-quality-v2` и предварительная метка
  `power-quality-v2-profile` опубликованы. Profile-only configs проверяют
  Ollama 0.35.0, digest и полное GPU-размещение обеих Q4-моделей; коллегам
  производственные прогоны по этой метке запрещены.
