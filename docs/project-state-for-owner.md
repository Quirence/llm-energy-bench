# Состояние проекта для владельца

Дата среза: 2026-09-30.

## Короткий ответ

Техническая часть, необходимая для начала полноценного черновика статьи,
готова. Собраны и проверены два основных стенда, три calibration launch на
каждом, отдельное наблюдение GTX 1080 и воспроизводимый итоговый анализ. После
review и merge текущей ветки датасет следует пометить тегом `paper-dataset-v1`
и больше не менять задним числом.

## Что создано

`llm-energy-bench` — CLI-инструмент на Python 3.12 для последовательного warm
LLM-инференса через Ollama. Он измеряет latency, TTFT, prompt/output tokens,
throughput, NVML power/energy, joules/token, tokens/joule, temperature, power
limit и VRAM. В проекте нет dashboard, сервера или маркетинговой платформы.

Реализованы:

- строгие TOML и prompt-set contracts;
- Ollama preload, streaming, TTFT и контроль полного размещения на GPU;
- NVML capability probe, request-scoped telemetry и проверяемые fallback paths;
- schema v2 с auditable warm-up, template cache floor и model-reload gate;
- атомарные raw artifacts, SHA-256, gzip, privacy и size guards;
- fail-closed validator и детерминированные CSV/Markdown reports;
- `analyze`, который не позволяет смешать calibration, primary benchmark и
  observation-only evidence;
- статистический анализ ratio-of-sums, equal-prompt quality, sample CV,
  repeatability threshold и paired hierarchical bootstrap для инверсий;
- Windows/Linux CI и 318 hardware-independent тестов на момент среза.

## Какие данные приняты

| Роль | GPU | Calibration | Benchmark | Статус |
| --- | --- | ---: | ---: | --- |
| Primary A | RTX 5060 Laptop | 3 × 18/18 | 480/480 | принят |
| Primary B | RTX 4060 Ti | 3 × 18/18 | 480/480 | принят |
| Observation | GTX 1080 | — | 480/480 | отдельно от verdict |

Оба primary benchmark используют Ollama 0.34.2, commit
`d587a5d6fbeae039009a4e722f2af1249ebcbbf4`, одинаковый prompt set, logical
prompt map и четыре точных model digest. Первый неудачный RTX 4060 Ti launch
с двумя отсутствующими `load_duration` сохранён для аудита, но в анализ не
входит.

## Итог научной проверки

- Верхние speed- и energy-ranks совпали в 6/6 primary `host × workload` blocks.
- Во всех шести блоках лидирует `llama3.2:3b-instruct-q4_K_M`.
- Среди всех допустимых пар нет описательной speed/energy rank inversion;
  следовательно, нет и material inversion с ненулевым bootstrap CI.
- Предзарегистрированная гипотеза имеет итог `not_supported` **в исследованной
  области**, а не опровергнута универсально.
- Llama Q8 показывает важное вторичное наблюдение: quality 0.750 на RTX 5060 и
  0.725 на RTX 4060 Ti при одинаковых prompt, seed, runtime и digest. Поэтому
  eligibility применяется по хосту.
- Material thresholds: RTX 5060 — 14.32% short, 8.97% long, 23.16% scored;
  RTX 4060 Ti — 5.00%, 12.47%, 63.14% соответственно.

Смысл для статьи: на двух исследованных GPU оптимизация только по скорости уже
выбрала ту же конфигурацию, что и GPU-energy efficiency. Поэтому нельзя обещать
отдельную экономию от energy-aware ranking на этой матрице. Научная ценность —
в проверяемой методике, воспроизводимом отрицательном результате и выявленных
границах измерения/качества.

## Кто что сделал

- **Quirence/Codex**: исследовательский протокол, runner, schema/validation,
  cache/load gates, интеграция, RTX 5060 campaigns, финальный статистический
  анализ и документация.
- **Qcsteeven (Лев)**: ранние package/CI и data contracts, основная NVML
  telemetry/fallback реализация, три RTX 4060 Ti calibration launch и оба
  desktop benchmark attempts, включая принятый 480/480 run.
- **Skipl1 (Димас)**: Ollama inventory/preload/streaming/TTFT, live-runtime
  проверки и диагностика cache/reload behavior, независимые reviews и
  GTX 1080 observation 480/480.

Проценты строк кода не следует переносить в статью как авторский вклад: merge
и последующая переработка сильно искажают такую метрику. Для author
contributions лучше использовать роли выше.

## Где брать числа

- Итог: `experiments/studies/paper-dataset-v1/analysis.json`.
- Краткий читаемый результат: `experiments/studies/paper-dataset-v1/report.md`.
- Calibration table: `experiments/studies/paper-dataset-v1/calibration.csv`.
- Полные request-level данные: соответствующие директории в
  `experiments/runs/`.
- Хронология решений и отклонённых запусков: `docs/experiment-log.md`.
- Каркас статьи: `docs/paper-draft.md`.

## Что можно и нельзя писать

Можно:

- «в исследованной области speed- и GPU-energy ranking выбрали одного лидера»;
- «гипотеза о material rank inversion не поддержана на двух primary GPU»;
- «методика фиксирует runtime, digest, prompt map, quality и telemetry»;
- «quality eligibility одной конфигурации различалась между хостами».

Нельзя:

- «energy-aware выбор бесполезен для любых LLM/GPU»;
- «измерена энергия/стоимость всего кластера»;
- «NVML заменяет внешний ваттметр»;
- включать GTX 1080 в знаменатель primary verdict;
- подменять отсутствие обнаруженного эффекта доказанной эквивалентностью.

## Что осталось организационно

1. Qcsteeven и Skipl1 проверяют финальный PR, особенно attribution, hardware
   conditions и интерпретацию собственных прогонов.
2. После approval PR вливается в `main` и merge commit получает annotated tag
   `paper-dataset-v1`.
3. Выбирается журнал и форматирование; источники проверяются по оригинальным
   статьям, стандартам и официальной документации.
4. Авторы заполняют свои разделы из `docs/paper-draft.md`, не меняя frozen
   artifacts и decision rule.
5. Внешний ваттметр остаётся отдельным будущим экспериментом, если журнал или
   рецензент потребует wall-system energy.
