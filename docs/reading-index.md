# Индекс материалов для статьи

Дата проверки ссылок: 2026-10-01.

Цель списка — не собрать «всё про Green AI», а дать минимальную библиографию,
которая позволяет обосновать исследовательский вопрос, измерительную методику,
выбор метрик, статистическую обработку и ограничения результата. Идентификаторы
`R01`–`R20` стабильны: их можно использовать в заметках до выбора стиля
библиографии журнала.

## Как читать

Для каждого источника выписывать четыре пункта:

1. какой вопрос решают авторы;
2. что именно и на каком оборудовании они измеряют;
3. какие метрики и статистику используют;
4. где наш дизайн совпадает, а где отличается.

Не переносить в текст статьи численные результаты с другого hardware/runtime как
ожидаемый результат нашей работы. Они нужны для постановки вопроса и сравнения
методик.

## Приоритет A — прочитать до написания методики и related work

| ID | Источник | Зачем нам | Что читать в первую очередь |
| --- | --- | --- | --- |
| R01 | Samsi et al. [From Words to Watts: Benchmarking the Energy Costs of Large Language Model Inference](https://arxiv.org/abs/2310.03003), HPEC 2023 | Ближайшая по теме работа: LLM inference, performance и energy на разных GPU | experimental setup, energy/token, влияние model size, batch и sharding, limitations |
| R02 | Luccioni, Jernite, Strubell. [Power Hungry Processing: Watts Driving the Cost of AI Deployment?](https://arxiv.org/abs/2311.16863), FAccT 2024 | Показывает, почему inference следует измерять отдельно от training и почему важна функциональная нагрузка | единица сравнения, scope энергии, связь task/model и стоимости inference |
| R03 | Fernandez et al. [Energy Considerations of Large Language Model Inference and Efficiency Optimizations](https://arxiv.org/abs/2504.17674), 2025 | Современное исследование зависимости energy gains от workload geometry, runtime и GPU | методика разбиения input/output lengths, online/offline regimes, ограничения FLOP-прокси |
| R04 | NVIDIA. [NVML API Reference Guide](https://docs.nvidia.com/deploy/nvml-api/latest/) | Первичный источник для power, total energy, temperature, memory и power limit | `nvmlDeviceGetPowerUsage`, `nvmlDeviceGetTotalEnergyConsumption`, единицы и hardware-dependent semantics |
| R05 | Ollama. [API usage metrics](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx) | Первичный источник для `total_duration`, `load_duration`, prompt/decode counts и durations | streaming final chunk, nanosecond durations, cached prompt count, формула eval tok/s |
| R06 | Kalibera, Jones. [Rigorous Benchmarking in Reasonable Time](https://kar.kent.ac.uk/33611/), ISMM 2013, DOI 10.1145/2464157.2464160 | Обоснование независимых запусков, уровней вариативности и иерархического resampling | experimental dimensions, repetitions, confidence intervals, cost/precision trade-off |
| R07 | Pineau et al. [Improving Reproducibility in Machine Learning Research](https://jmlr.org/papers/v22/20-303.html), JMLR 2021 | Чек-лист воспроизводимости: code, data, exclusions, hardware, runs, uncertainty | reproducibility checklist и требования к empirical results |
| R08 | Henderson et al. [Towards the Systematic Reporting of the Energy and Carbon Footprints of Machine Learning](https://jmlr.org/papers/v21/20-312.html), JMLR 2020 | Обоснование прозрачной фиксации hardware/software и границ energy/carbon claims | reporting framework, system boundary, real-time energy tracking, limitations |
| R09 | Frantar et al. [GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers](https://arxiv.org/abs/2210.17323), ICLR 2023 | Теоретический и экспериментальный фон для weight-only low-bit quantization | постановка PTQ, accuracy/compression trade-off, почему меньше бит не гарантирует пропорциональную скорость |
| R10 | Lin et al. [AWQ: Activation-aware Weight Quantization for On-Device LLM Compression and Acceleration](https://proceedings.mlsys.org/paper_files/paper/2024/file/42a452cbafa9dd64e9ba4aa95cc1ef21-Paper-Conference.pdf), MLSys 2024 | Близко к локальному/on-device сценарию и consumer/edge hardware | salient weights, memory bandwidth, end-to-end acceleration и quality evaluation |

## Приоритет B — для обсуждения результатов и ограничений

| ID | Источник | Зачем нам | Связь с нашей работой |
| --- | --- | --- | --- |
| R11 | You, Chung, Chowdhury. [Zeus: Understanding and Optimizing GPU Energy Consumption of DNN Training](https://www.usenix.org/conference/nsdi23/presentation/you), NSDI 2023 | Хороший пример того, что speed optimum и energy optimum могут расходиться | У нас проверяется сходный инженерный вопрос, но для single-request warm inference, а не training |
| R12 | Yang et al. [Part-time Power Measurements: NVIDIA-SMI's Lack of Attention](https://arxiv.org/abs/2312.02741), 2023 | Критическая работа о sampling и ограничениях NVIDIA power telemetry | Нужна для честного ограничения 100-мс NVML samples и аргумента в пользу wattmeter validation |
| R13 | MLCommons. [MLPerf Inference Power Measurement Rules](https://github.com/mlcommons/inference_policies/blob/master/power_measurement.adoc) | Эталон более сильной wall-power methodology | Показывает, почему наши значения называются GPU-only, а не system energy/TCO |
| R14 | Efron, Tibshirani. [Bootstrap Methods for Standard Errors, Confidence Intervals, and Other Measures of Statistical Accuracy](https://doi.org/10.1214/ss/1177013815), Statistical Science 1986 | Базовый источник для bootstrap и percentile CI | Основание resampling, но конкретная иерархия prompt→repetition задаётся нашим дизайном |
| R15 | Georges, Buytaert, Eeckhout. [Statistically Rigorous Java Performance Evaluation](https://doi.org/10.1145/1297027.1297033), OOPSLA 2007 | Практика warm-up/steady state и статистически строгих performance experiments | Полезно для объяснения, почему cold load отделён от measured warm inference |
| R16 | Fleming, Wallace. [How Not to Lie with Statistics: The Correct Way to Summarize Benchmark Results](https://cgi.cse.unsw.edu.au/~cs9242/20/papers/Fleming_Wallace_86.pdf), CACM 1986 | Предупреждает о некорректном усреднении benchmark ratios | Сопоставить с нашим `Σtokens/Σtime` и `Σtokens/Σenergy`; не смешивать разные workload blocks |
| R17 | Kwon et al. [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://doi.org/10.1145/3600006.3613165), SOSP 2023 | Контекст современных serving runtimes, KV cache и batching | Объясняет, почему выводы concurrency=1/Ollama нельзя переносить на vLLM batching |
| R18 | Dettmers et al. [LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale](https://papers.neurips.cc/paper_files/paper/2022/hash/c3ba4962c05c49636d4c6206a97e9c8a-Abstract-Conference.html), NeurIPS 2022 | Фон для 8-bit inference и mixed-precision outliers | Не описывает GGUF Q8_0 напрямую, но даёт корректный общий контекст quantization |

## Приоритет C — первичные материалы о конкретной экспериментальной системе

| ID | Материал | Для какого фрагмента статьи |
| --- | --- | --- |
| R19 | Qwen Team. [Qwen3 Technical Report](https://arxiv.org/abs/2505.09388), 2025 | Описание семейства Qwen3 и границ переноса результатов с 4B Instruct |
| R20 | Meta. [Llama 3.2 Model Card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md) | Описание Llama 3.2 3B Instruct, intended use и model limitations |
| M01 | llama.cpp. [Quantize tool documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md) | Что означают GGUF quantization и accuracy/memory trade-off; это документация, не peer-reviewed статья |
| M02 | Ollama. [OpenAPI schema](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml) | Точные поля API и единицы измерения |
| M03 | MLCommons. [Power Measurement guide](https://docs.mlcommons.org/inference/power/) | Практическая схема внешнего power analyzer и граница system under test |

## Рекомендуемый порядок

1. `R01`, `R02`, `R03` — понять поле LLM inference energy.
2. `R04`, `R05`, `R12`, `R13` — проверить границы измерения.
3. `R06`, `R07`, `R14`, `R15`, `R16` — подготовить методику и статистику.
4. `R09`, `R10`, `R18`, `M01` — написать раздел о quantization.
5. `R17` — сформулировать границу single-request Ollama против batched serving.
6. `R19`, `R20` — описать конкретные модели без рекламных формулировок.

## Карта «источник → раздел черновика»

| Раздел | Основные IDs |
| --- | --- |
| Введение и мотивация | R01, R02, R08 |
| Связанные работы по inference energy | R01, R02, R03, R11 |
| Модели и quantization | R09, R10, R18, R19, R20, M01 |
| Runtime, TTFT, prefill/decode, cache | R05, R17, M02 |
| NVML и system boundary | R04, R12, R13, M03 |
| Повторяемость и статистика | R06, R07, R14, R15, R16 |
| Ограничения и внешняя валидность | R03, R08, R12, R13, R17 |

## Что пока не использовать как основную опору

- новости, корпоративные блоги и калькуляторы без raw methodology;
- оценки «один запрос равен X ватт-часов» без model, token counts, hardware и
  system boundary;
- training-energy papers как прямое доказательство inference-energy behavior;
- TDP вместо измеренной power/energy;
- более новые статьи только потому, что у них большие проценты экономии: сначала
  проверять peer-review status, workload и measurement boundary.
