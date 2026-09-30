# Черновик статьи: структура и распределение работы

Статус: каркас с замороженным двухстендовым датасетом и воспроизводимым
итоговым анализом. Числа для раздела результатов берутся из
`experiments/studies/paper-dataset-v1/analysis.json`; литературный обзор и
оформление под выбранный журнал ещё не выполнены.

## Рабочее название

**Сравнение локального LLM-инференса по производительности и GPU-энергии:
воспроизводимый эксперимент на потребительских NVIDIA GPU**

Название не предполагает заранее, что energy-aware и speed-only ranking
различаются.

## Исследовательский вопрос

Меняется ли инженерный выбор локальной LLM-конфигурации, если вместе со
скоростью учитывать GPU energy/request, joules/output token и output
tokens/joule при заданном минимуме качества?

Нулевая по смыслу возможность — rankings практически совпадут. Такой результат
считается допустимым и не заменяется постфактум более удобной гипотезой.

## Авторы и зоны первого черновика

| Участник | Раздел первого черновика | Экспериментальная зона |
| --- | --- | --- |
| Quirence | постановка задачи, гипотеза, общий дизайн, ограничения, интеграция текста | RTX 5060 Laptop |
| Qcsteeven (Лев) | NVML, источники power/energy, fallback и погрешности измерения | RTX 4060 Ti desktop |
| Skipl1 (Димас) | Ollama streaming, TTFT, cache-floor, runtime failures и model reload | GTX 1080 observation |

Все авторы совместно проверяют методику, таблицы результатов и финальные
формулировки. Эта таблица распределяет первый текст, а не определяет порядок
авторов или процент научного вклада.

## 1. Введение

- Локальный LLM-инференс выбирают не только по времени ответа, но также по
  энергии, ограничениям GPU и стоимости эксплуатации.
- Объект исследования: одиночный последовательный warm inference через Ollama.
- Предмет: связь performance-, quality- и GPU-energy-метрик при выборе
  model/quantization configuration.
- Проверяемая гипотеза и заранее допустимый отрицательный результат.
- Вклад работы формулируется как методика и воспроизводимый инструмент, а не
  как утверждение о нехватке «решения на рынке».

## 2. Связанные работы

TODO до первого литературного поиска:

- стандарты и методики energy measurement для вычислительных нагрузок;
- LLM inference benchmarking и разделение prefill/decode;
- quantization и влияние на throughput/quality/energy;
- ограничения NVML по сравнению с внешним ваттметром.

В этот раздел включаются только проверенные источники с точными ссылками.

## 3. Методика

### 3.1. Стенды

| Роль | GPU | Статус данных |
| --- | --- | --- |
| Primary A | RTX 5060 Laptop | основной двухстендовый анализ |
| Primary B | RTX 4060 Ti desktop | основной двухстендовый анализ |
| Observation | GTX 1080 | внешняя наблюдательная проверка, без включения в primary blocks |

Driver, power limit, VRAM, temperature, runtime version, model digest и
telemetry capabilities берутся из manifest, а не переписываются вручную.

### 3.2. Зафиксированные условия pilot-v1

- Python 3.12, Ollama 0.34.2;
- `llama3.2:3b-instruct-q4_K_M` с полным digest из конфигурации;
- context 4096, temperature 0, seed 42, concurrency 1, KV cache f16;
- 4 исключённых warm-up и 3 measured repetitions;
- 6 prompts: short, long/prefill и scored utility;
- только полное размещение модели на GPU.

### 3.3. Метрики

- latency, TTFT, prompt/output token counts;
- prefill, decode и end-to-end throughput;
- average/observed peak GPU power и GPU energy/request;
- joules/output token и output tokens/joule;
- GPU-only estimate стоимости 1M output tokens при заданном тарифе;
- temperature, power limit и VRAM как контекст измерения.

### 3.4. Валидность

Описать schema v2, четыре auditable warm-up, cache-floor с допуском одного
marker-boundary token, запрет model reload, telemetry coverage, frozen digest,
artifact hashes и исключение всего invalid run из агрегатов.

## 4. Экспериментальная процедура

1. Получить один tagged baseline на всех стендах.
2. Выполнить `doctor` и не продолжать при любом drift.
3. Выполнить по три независимых pilot/calibration launch на primary hosts.
4. Выполнить один observation launch на GTX 1080.
5. Зафиксировать четыре model digests и только затем включить `benchmark-v1`.
6. Выполнить основную матрицу на обоих primary hosts.
7. Строить агрегаты только из run directories с `validation.ok=true`.

## 5. Результаты

### 5.1. Повторяемость pilot/calibration

На каждом primary GPU выполнено по три независимых `pilot-v1` запуска. Для
каждой категории сначала вычислялись run-level `Σtokens/Σtime` и
`Σtokens/Σenergy`, затем выборочный CV между тремя запусками. Материальным
считался эффект не меньше `max(5%, 3 × max(CV_speed, CV_energy))`.

| Стенд | short | long | scored |
| --- | ---: | ---: | ---: |
| RTX 5060 Laptop | 14,32% | 8,97% | 23,16% |
| RTX 4060 Ti | 5,00% | 12,47% | 63,14% |

Высокий scored-порог на RTX 4060 Ti связан с двухтокенными ответами длительностью
около 40–50 мс и малым числом 100-мс telemetry samples. Поэтому scored-блок
имеет заметно меньшую способность обнаруживать умеренные энергетические эффекты.

### 5.2. Основная матрица

Оба primary runs выполнены на Ollama 0.34.2 от `benchmark-v1-code-v5` и прошли
валидацию 480/480. Prompt set, logical prompt map и четыре model digest совпадают.

| Стенд | Quality-eligible конфигурации | Лидер tok/s и tok/J |
| --- | ---: | --- |
| RTX 5060 Laptop | 4/4 | Llama 3.2 Q4 |
| RTX 4060 Ti | 3/4 | Llama 3.2 Q4 |

На RTX 5060 оценки качества равны 1,0 для Qwen Q4/Q8, 0,85 для Llama Q4 и
0,750 для Llama Q8. На RTX 4060 Ti первые три значения сохраняются, а Llama Q8
получает 0,725 и исключается только на этом хосте. Это host-local quality gate,
а не удаление конфигурации из другого стенда.

В каждой из шести комбинаций `host × workload` верхнее место по output tok/s и
output tok/J занимает Llama 3.2 Q4. Полные агрегаты находятся в
`analysis.json`; latency, TTFT, prefill/decode, power и temperature — в
`summary.csv` соответствующих run directories.

### 5.3. Rank inversion

Aggregate speed- и energy-top совпали в 6/6 primary blocks (100%). Проверка всех
пар quality-eligible конфигураций не обнаружила даже описательной смены порядка,
поэтому кандидатов на material inversion и paired hierarchical bootstrap нет.

По заранее зафиксированному правилу (не менее 90% совпадений top и отсутствие
устойчивых material inversions) гипотеза **не поддержана в исследованной
области**. Корректная формулировка не равна «энергетическая оптимизация никогда
не меняет выбор»: она ограничена двумя GPU, Ollama 0.34.2, четырьмя
model/quantization configurations и данным prompt set.

GTX 1080 показывается отдельно как observation и не увеличивает знаменатель
основного двухстендового вывода.

## 6. Обсуждение и ограничения

- NVML измеряет GPU, а не wall-system energy;
- два primary GPU не представляют весь класс оборудования;
- один runtime и ограниченный prompt set;
- качество проверяется небольшим deterministic utility subset;
- runtime/model digest и thermal state ограничивают переносимость;
- отсутствие material inversion не доказывает универсальную эквивалентность.

## 7. Заключение

В исследованной области учёт GPU-energy не изменил лучший инженерный выбор по
сравнению со speed-only ranking: Llama 3.2 Q4 лидировала по обеим метрикам во
всех шести primary blocks. Практическая ценность результата — не в обещанной
экономии, а в измерительной методике, отрицательном результате и наблюдении,
что quality eligibility одной конфигурации различалась между GPU даже при
совпадающих seed, prompt text, runtime и digest.

## Контроль заполнения

- [x] PR #17 merged и merge commit tagged `pilot-v1-code`.
- [x] Все три участника работали от зафиксированных runtime/model contracts.
- [x] Три validated launch на каждом primary host.
- [x] Один validated GTX 1080 observation launch.
- [x] Benchmark digests предзарегистрированы до основной кампании.
- [x] Два совместимых primary benchmark: по 480/480 valid.
- [x] Финальный RTX 5060 benchmark с byte-identical cross-host markers.
- [x] Result PRs содержат raw artifacts, hashes и experiment-log entries.
- [x] Числа воспроизводятся из committed artifacts командой `analyze`.
- [x] Вывод ограничен исследованной областью и GPU-only NVML energy.
- [ ] Подобраны и проверены литературные источники.
- [ ] Текст оформлен по требованиям выбранного журнала.
