# Состояние проекта для владельца

Дата среза: 2026-09-28.

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

## Кто что сделал

Функциональная атрибуция важнее числа строк:

- **Quirence/Codex**: исследовательский протокол, runner, интеграция,
  validation/reporting, GPU-placement и NVML sanity gates, документация,
  RTX 5060 acceptance и финальная стабилизация.
- **Qcsteeven (Лев)**: package/CI и config/result contracts на раннем этапе,
  основная NVML telemetry-реализация, fallback sources, RTX 4060 Ti
  диагностические прогоны и первая реализация rank-inversion анализа.
- **Skipl1 (Димас)**: Ollama inventory/preload/streaming/TTFT boundary, live
  runtime-проверка, GTX 1080 диагностика и обнаружение cold reload после падения
  runtime.

Для ориентировочного технического среза на интеграционном коммите `a683a57`
доля добавленных строк была около 49% Quirence, 33% Qcsteeven и 18% Dimas
(имена `Dimas` и `Skipl1` объединены). Это **не оценка научного вклада**:
метрика зависит от тестов, документации, merge history и последующей
переработки. В статье вклад лучше описывать по ролям выше.

## Что показало ревью веток

- **PR #17** — правильная точка консолидации, но исходная версия имела ошибки
  aggregate prefill, fail-open schema validation, неаудируемый cache floor и
  не отбрасывала cold reload. Исправления включены в текущую стабилизацию.
- **PR #18** — не готов к merge: мог использовать невалидные run directories,
  смешивать разные model digests, сравнивать неполные prompt sets и выдавать
  ложный вывод «гипотеза не поддержана». Требования сохраняются в Issue #6.
- **PR #19** — полезная RTX 4060 Ti диагностика, но ветка без отдельного
  решения меняла исходную RTX 4060 матрицу и не содержала raw artifacts.
- **PR #22** — полезная GTX 1080 диагностика, но ветка наследовала #19, а один
  calibration run содержал cold reload. Исследовательские выводы отброшены.

## Что сейчас нельзя утверждать

- Что speed- и energy-ranking совпадают или различаются на основной матрице.
- Что RTX 4060 Ti автоматически заменяет запланированную RTX 4060.
- Что NVML energy равна wall-system energy.
- Что локальные незакоммиченные прогоны образуют публикационный датасет.

## Когда база считается закреплённой

1. PR #17 получает approval и зелёный CI на Windows/Linux.
2. PR #17 squash-merge в `main`.
3. Merge commit получает тег `pilot-v1-code`.
4. Оба основных участника создают result branches именно от этого тега.
5. Pilot run имеет 18/18 valid measured requests и `validation.json: ok=true`.

На текущем MAIBENBEN preflight уже подтверждает RTX 5060, NVML, полный GPU
placement и правильный model digest, но установлен Ollama 0.34.4 вместо
согласованного 0.34.2. Инструмент правильно блокирует такой запуск. Перед
публикационным pilot нужно либо вернуть 0.34.2, либо отдельным решением изменить
версию протокола сразу для всех стендов и повторить preflight.

## Команды после появления тега

```text
git fetch origin --prune --tags
git switch main
git pull --ff-only origin main
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
