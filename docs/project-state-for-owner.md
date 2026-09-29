# Состояние проекта для владельца

Дата среза: 2026-09-29.

## Что представляет собой проект

`llm-energy-bench` — CLI-стенд на Python 3.12 для воспроизводимого измерения
локального Ollama-инференса. Он сохраняет latency, TTFT, token counts,
throughput, NVML power/energy, joules/token, tokens/joule, температурный и
VRAM-контекст. Это измерительный инструмент, а не веб-платформа и не готовое
«решение для ЦОД».

Исследовательская гипотеза остаётся прежней: energy-aware ranking может
отличаться от speed-only ranking. Отрицательный результат допустим и должен
быть зафиксирован без расширения гипотезы задним числом.

## Что уже реализовано

- CLI: `doctor`, `run`, `report`, фиксированные exit codes.
- Строгая TOML-конфигурация и versioned JSONL prompt sets.
- Ollama preload/inventory, проверка полного GPU placement, streaming, TTFT,
  token/runtime counters и сохранение частичных ошибок.
- NVML capability probe, request-scoped sampling и проверяемые fallback-пути:
  total-energy counter → instantaneous power → legacy power.
- Атомарные JSON/JSONL/gzip artifacts, hashes, privacy scan и лимит размера.
- Последовательный runner с deterministic request order, warm-up и немедленной
  записью каждого запроса, ответа и telemetry.
- Schema v2: четыре warm-up записи, проверяемый cache floor, допуск только
  одного служебного cache token и запрет холодного model reload в measured run.
- Validator, который независимо перепроверяет digests, placement, hashes,
  counts, cache, load duration, telemetry и energy.
- CSV/Markdown report с ratios of sums, median/IQR, quality floor и ranking
  только внутри одного GPU/host workload block.
- CI для Windows/Linux и hardware-independent fake implementations.
- Зафиксированный срез проходит 300 автоматических тестов.
- Тег `pilot-v1-code` указывает на merge commit `0ffc091`; это единственная
  кодовая база для сравнимых pilot-запусков.
- Schema-v2 наблюдение Dimas на GTX 1080 принято через PR #23: 18/18 запросов
  валидны, raw hashes воспроизводятся, но данные не входят в primary matrix.

## Кто что сделал

Функциональная атрибуция важнее числа строк:

- **Quirence/Codex**: исследовательский протокол, runner, интеграция,
  validation/reporting, GPU-placement и NVML sanity gates, документация,
  RTX 5060 acceptance и финальная стабилизация.
- **Qcsteeven (Лев)**: package/CI и config/result contracts на раннем этапе,
  основная NVML telemetry-реализация, fallback sources, RTX 4060 Ti
  диагностические прогоны и первая реализация rank-inversion анализа.
- **Skipl1 (Димас)**: Ollama inventory/preload/streaming/TTFT boundary, live
  runtime-проверка, обнаружение cold reload после падения runtime, независимый
  approval финальной стабилизации и validated GTX 1080 observation.

Для ориентировочного технического среза на интеграционном коммите `a683a57`
доля добавленных строк была около 49% Quirence, 33% Qcsteeven и 18% Dimas
(имена `Dimas` и `Skipl1` объединены). Это **не оценка научного вклада**:
метрика зависит от тестов, документации, merge history и последующей
переработки. В статье вклад лучше описывать по ролям выше.

## Что показало ревью веток

- **PR #17** — утверждённая точка консолидации. Во время ревью исправлены
  aggregate prefill, fail-open schema validation, неаудируемый cache floor и
  пропуск cold reload; PR одобрен Dimas, прошёл CI и влит в `main`.
- **PR #18** — закрыт без merge: мог использовать невалидные run directories,
  смешивать разные model digests, сравнивать неполные prompt sets и выдавать
  ложный вывод «гипотеза не поддержана». Требования сохраняются в Issue #6.
- **PR #19** — закрыт без merge; полезная RTX 4060 Ti диагностика не содержала
  raw artifacts. Само железо позже было внесено в протокол отдельной
  предрегистрационной поправкой до сбора публикационных данных.
- **PR #22** — закрыт без merge; полезная GTX 1080 диагностика, но ветка
  наследовала #19, а один calibration run содержал cold reload.
  Исследовательские выводы отброшены.
- **PR #23** — влит после независимой перепроверки. Он содержит один валидный
  schema-v2 GTX 1080 observation-run и защиту byte-exact артефактов от Windows
  EOL-конверсии.

## Что сейчас нельзя утверждать

- Что speed- и energy-ranking совпадают или различаются на основной матрице.
- Что старые локальные прогоны RTX 4060 Ti автоматически стали публикационными.
- Что NVML energy равна wall-system energy.
- Что локальные незакоммиченные прогоны образуют публикационный датасет.

## Состояние закрепления базы

Выполнено:

1. PR #17 получил approval и зелёный CI на Windows/Linux.
2. PR #17 squash-merged в `main` как `0ffc091`.
3. Merge commit получил тег `pilot-v1-code`.
4. Dimas опубликовал observation-only run с 18/18 valid measured requests и
   `validation.json: ok=true`.

Следующий gate: Quirence и Qcsteeven создают result branches именно от тега и
получают по три независимых validated launch на основных стендах.

На текущем MAIBENBEN preflight уже подтверждает RTX 5060, NVML, полный GPU
placement и правильный model digest, но установлен Ollama 0.34.4 вместо
согласованного 0.34.2. Инструмент правильно блокирует такой запуск. Перед
публикационным pilot нужно либо вернуть 0.34.2, либо отдельным решением изменить
версию протокола сразу для всех стендов и повторить preflight.

## Команды для запуска от зафиксированного тега

```text
git fetch origin --prune --tags
git switch --detach pilot-v1-code
git rev-parse HEAD
git tag --points-at HEAD
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install ".[dev]"
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m llm_energy_bench doctor --config configs/pilot-rtx5060.toml --json
.venv\Scripts\python -m llm_energy_bench run --config configs/pilot-rtx5060.toml
```

Для второго основного хоста используется его отдельный committed config.
Эксперимент нельзя публиковать, если tag, Ollama version, digest, prompt hash,
placement или validation отличаются от frozen baseline.
