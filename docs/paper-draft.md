# Черновик статьи: структура и распределение работы

Статус: каркас с первым принятым primary-host run. Итоговый вывод о гипотезе
откладывается до совместимого RTX 4060 Ti run и предзарегистрированного
bootstrap/material-effect анализа.

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

Заполняется после review result PRs.

### 5.1. Повторяемость pilot/calibration

TODO: median/IQR и CV по host × workload category.

### 5.2. Основная матрица

Принятый RTX 5060 run:
`benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1`, 480/480 valid,
Ollama 0.34.2, tag `benchmark-v1-code-v3`. Все четыре конфигурации прошли
quality floor: Qwen3 Q4/Q8 — 1.0, Llama 3.2 Q4 — 0.825, Llama 3.2 Q8 — 0.75.

Наблюдаемые aggregate speed/energy ranks совпали во всех трёх workload blocks:

| Workload | Порядок от лучшего к худшему по tok/s и tok/J |
| --- | --- |
| long | Llama Q4 → Qwen Q4 → Llama Q8 → Qwen Q8 |
| scored | Llama Q4 → Llama Q8 → Qwen Q4 → Qwen Q8 |
| short | Llama Q4 → Qwen Q4 → Llama Q8 → Qwen Q8 |

Диапазон Llama Q4: 83.402–122.719 output tok/s и 1.041–1.553 output tok/J.
Диапазон Qwen Q8: 32.967–67.148 output tok/s и 0.412–0.858 output tok/J.
Полные latency, TTFT, prefill/decode, power, energy и temperature values берутся
из committed `summary.csv`, а не округлённого текста этого раздела.

Из 480 запросов 468 использовали instantaneous-power integration, 12 —
total-energy counter после sanity check. Sensitivity-пересчёт всех запросов
только по instantaneous power сохранил каждый energy rank. Внешней wall-energy
валидации это не заменяет.

### 5.3. Rank inversion

На RTX 5060 aggregate speed- и energy-top совпали в 3/3 блоках. Это ещё не
проверка material inversion: TODO остаются effect threshold
`max(5%, 3 × repeatability CV)`, bootstrap 95% CI и совместимый второй primary
host. Поэтому текущая формулировка — «инверсия не наблюдалась на одном стенде»,
а не «гипотеза опровергнута».

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

Формулируется условно после анализа:

- если есть устойчивая material inversion — указать точные hosts/workloads и
  размер эффекта без обобщения за пределы матрицы;
- если rankings совпадают минимум в 90% blocks и устойчивых инверсий нет —
  сообщить, что гипотеза не поддержана в исследованной области.

## Контроль заполнения

- [x] PR #17 merged и merge commit tagged `pilot-v1-code`.
- [ ] Все три участника подтвердили commit, Python, Ollama и model digest.
- [ ] Три validated launch на каждом primary host.
- [x] Один validated GTX 1080 observation launch.
- [x] Benchmark digests предзарегистрированы до основной кампании.
- [x] RTX 5060 benchmark: 480/480 valid из frozen v3 tag.
- [ ] Result PRs содержат raw artifacts, hashes и experiment-log entries.
- [ ] Числа в тексте воспроизводятся из committed `summary.csv`/report command.
- [ ] Вывод не сильнее собранных данных.
