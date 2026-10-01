# Отчёт по методике и формулам

Дата среза: 2026-10-01. Этот документ описывает фактически реализованную и
применённую методику `paper-dataset-v1`, а не желаемый будущий дизайн. Numeric
source of truth — `experiments/studies/paper-dataset-v1/analysis.json`.

## 1. Объект и граница измерения

Измеряется последовательный (`concurrency = 1`) warm inference одного локального
LLM через Ollama 0.34.2. Основная единица наблюдения — один request с одним
prompt, одной model/quantization configuration и одним repetition.

Энергетическая граница — GPU и связанная с ним память/схемы в том объёме, который
видит NVML. CPU, RAM, SSD, дисплей, VRM losses и блок питания не входят. Поэтому
везде используется формулировка **GPU energy**, а стоимость — **GPU-only
estimate**. Полная system/wall energy требует внешнего ваттметра.

## 2. Зафиксированные факторы

- primary GPU: RTX 5060 Laptop и RTX 4060 Ti desktop;
- observation-only: GTX 1080, вне primary verdict;
- runtime: Ollama 0.34.2;
- `num_ctx = 4096`, `temperature = 0`, seed 42, KV cache f16;
- четыре model/quantization configurations с точными digest;
- 24 prompts: `short`, `long`, `scored`;
- 5 repetitions основной матрицы, 3 repetitions calibration;
- четыре warm-up на модель, measured order детерминированно перемешан;
- только полное размещение модели на GPU.

Human-readable tag недостаточен: совместимость определяется digest, runtime,
code commit, prompt-set hash и logical prompt map.

## 3. Обозначения

Для запроса `i`:

- `L_i` — end-to-end latency, s;
- `F_i` — TTFT, s;
- `Nᵖ_i` — все prompt tokens;
- `Nᶜ_i` — cached prompt tokens;
- `Nᵘ_i = Nᵖ_i - Nᶜ_i` — uncached prompt tokens;
- `Nᵒ_i` — output tokens;
- `Dᵖ_i` — Ollama `prompt_eval_duration`, ns;
- `Dᵈ_i` — Ollama `eval_duration`, ns;
- `(t_{ik}, P_{ik})` — NVML sample time, s, и power, W;
- `E_i` — GPU energy запроса, J;
- `q_{ipr}` — score repetition `r` для scored prompt `p` и configuration `c`.

## 4. Временные метрики

Python использует monotonic clock вокруг streaming request.

```text
latency_i = t_end,i - t_start,i
TTFT_i    = t_first_nonempty_token,i - t_start,i
```

TTFT фиксирует первый непустой output chunk, а не открытие HTTP-соединения.

Runtime-specific rates:

```text
prefill_tok_s_i = Nᵘ_i / (Dᵖ_i / 10^9)
decode_tok_s_i  = Nᵒ_i / (Dᵈ_i / 10^9)
e2e_tok_s_i     = Nᵒ_i / L_i
```

`prefill_tok_s` использует только uncached prompt tokens. `e2e_tok_s` включает
весь наблюдаемый request latency и является primary speed metric.

## 5. GPU energy

### 5.1. Приоритет источников

1. NVML total-energy counter;
2. интеграл instantaneous power;
3. интеграл legacy/averaged power;
4. иначе request invalid.

Выбранный source и причина fallback записываются в каждом output record.

### 5.2. Total-energy counter

```text
E_i = C_last - C_first
```

где counter предварительно переводится из mJ в J. Delta должен быть
положительным и физически согласованным. Counter отклоняется, если:

```text
E_i / (t_last - t_first) > 1.2 × power_limit
```

или отношение counter delta к интегралу доступной power выходит за интервал
`[0.5, 2.0]`. После этого используется следующий доступный source.

### 5.3. Интегрирование power

Для отсортированных samples применяется trapezoidal rule:

```text
E_i = Σ_k (t_{k+1} - t_k) × (P_k + P_{k+1}) / 2
```

Нужно минимум два samples, времена должны быть монотонными, power не может быть
отрицательной или превышать `1.2 × power_limit`. Интервал sampling в конфиге —
100 мс; gap больше 500 мс делает request invalid.

### 5.4. Power summaries

```text
average_GPU_power_i = E_i / (t_last - t_first)
observed_peak_power_i = max_k(P_{ik})
```

Peak является максимальным **наблюдённым** sample, а не гарантированным
аппаратным пиком между samples.

## 6. Energy-efficiency и стоимость

Для request:

```text
J_per_output_token_i = E_i / Nᵒ_i
output_tokens_per_J_i = Nᵒ_i / E_i
```

При тарифе `R` currency/kWh:

```text
GPU_cost_per_1M_output_tokens_i =
    J_per_output_token_i × 1,000,000 / 3,600,000 × R
```

Без явно заданных tariff и currency cost равен `null`. В frozen campaigns тариф
не задавался, поэтому денежные выводы не делаются.

## 7. Валидация request и run

Request исключается при runtime error, отсутствии обязательных durations/TTFT,
нулевых output tokens/energy, плохой telemetry coverage, model reload, digest
drift или cache excess. Measured `load_duration > 100 ms` считается reload.

Ollama сохраняет template prefix в cache. Поэтому нулевой cached count не
требуется. Для каждой модели после cold warm-up берётся минимум cached count из
трёх следующих warm-ups:

```text
template_floor = min(cached_warmup_2, cached_warmup_3, cached_warmup_4)
cache_excess_i = max(0, Nᶜ_i - template_floor)
```

Допускается не более одного marker-boundary token. Validator независимо
перепроверяет schema, hashes, counts, GPU placement, runtime/model identity,
warm-ups, cache/load rules, telemetry и energy. В study analysis входит только
полностью valid completed run; отдельные valid rows из invalid run не спасаются.

## 8. Агрегация внутри configuration × host × workload

Latency и TTFT описываются median и IQR:

```text
IQR = Q_0.75 - Q_0.25
```

Quantiles вычисляются linear interpolation по отсортированным значениям.

Rates не усредняются как среднее request ratios. Используется ratio of sums:

```text
speed(c,h,w)      = Σ_i Nᵒ_i / Σ_i L_i
efficiency(c,h,w) = Σ_i Nᵒ_i / Σ_i E_i
J_per_token       = Σ_i E_i / Σ_i Nᵒ_i
prefill_rate      = Σ_i Nᵘ_i / (Σ_i Dᵖ_i / 10^9)
decode_rate       = Σ_i Nᵒ_i / (Σ_i Dᵈ_i / 10^9)
```

Запросы разных host или workload category не смешиваются в один rank.

## 9. Quality gate

Для каждого scored prompt сначала усредняются repetitions, затем prompts имеют
равный вес:

```text
Q_{c,h,p} = (1 / R_p) × Σ_r q_{c,h,p,r}
Q_{c,h}   = (1 / P) × Σ_p Q_{c,h,p}
```

Configuration допускается в ranking на данном host при:

```text
Q_{c,h} >= 0.75
```

Eligibility host-local. В frozen dataset Llama Q8 имеет 0.750 на RTX 5060 и
0.725 на RTX 4060 Ti, поэтому исключена только на втором хосте.

## 10. Calibration и порог материальности

Для каждого из трёх независимых calibration launches `j` вычисляются run-level
ratio-of-sums `S_j` (tok/s) и `G_j` (tok/J) отдельно по workload category.

Sample coefficient of variation:

```text
mean(x) = (1 / n) × Σ_j x_j
s(x)    = sqrt(Σ_j (x_j - mean(x))² / (n - 1))
CV(x)   = s(x) / mean(x)
```

Зарегистрированный практический порог:

```text
τ_{h,w} = max(0.05, 3 × max(CV_speed,h,w, CV_energy,h,w))
```

Это operational materiality rule, а не стандартный significance test. Он
защищает от объявления важным эффекта, сопоставимого с repeatability noise.

## 11. Rank inversion и paired hierarchical bootstrap

В каждом primary block `host × workload` configurations ранжируются отдельно
по `speed` и `efficiency`. Проверяются **все пары** eligible configurations, а
не только лидеры.

Для пары с разными порядками:

```text
Δ_speed  = speed(speed_winner) / speed(speed_loser) - 1
Δ_energy = efficiency(energy_winner) / efficiency(energy_loser) - 1
```

Bootstrap: 10 000 resamples, seed 42.

1. Из общих prompt IDs выбирается `P` prompts с возвращением.
2. Внутри каждого выбранного prompt выбираются repetition cells с возвращением.
3. Одни и те же prompt/repetition draws применяются к обеим configurations.
4. На каждом resample заново вычисляются ratio-of-sums и оба relative effects.
5. 95% percentile CI — 2.5-й и 97.5-й процентили с linear interpolation.

Inversion считается material, только если одновременно:

```text
Δ_speed  >= τ_{h,w}
Δ_energy >= τ_{h,w}
CI_low(Δ_speed)  > 0
CI_low(Δ_energy) > 0
```

В primary dataset описательных pairwise inversions нет, поэтому bootstrap не
может создать post-hoc candidate; число material inversions равно нулю.

## 12. Итоговое decision rule

```text
supported:
    существует хотя бы одна material pairwise inversion

not_supported:
    speed-top == energy-top минимум в 90% primary blocks
    AND material inversions отсутствуют

inconclusive:
    все остальные случаи
```

Фактически: 6/6 совпадающих blocks, 0 descriptive inversions, итог
`not_supported`. Это означает «гипотеза не поддержана в исследованной области»,
а не «ranking всегда совпадает» и не доказательство эквивалентности.

## 13. Воспроизводимые артефакты

- raw request/output/telemetry и manifest — `experiments/runs/<run-id>/`;
- per-run validation/report — в той же директории;
- study result — `experiments/studies/paper-dataset-v1/`;
- authoritative values — `analysis.json`;
- human summary — `report.md`;
- calibration table — `calibration.csv`.

CLI принимает calibration и benchmark inputs раздельно и требует ровно шесть
и два run directories соответственно. Третий observation-run не может
увеличить primary denominator. Две последовательные генерации study artifacts
дают byte-identical files.

## 14. Ограничения методики

- NVML — не внешний метрологически аттестованный wall meter;
- короткие requests могут покрываться малым числом power samples;
- total-energy counter и power telemetry имеют driver/GPU-dependent semantics;
- два primary GPU, один runtime и concurrency=1 ограничивают переносимость;
- utility quality set мал и не заменяет полноценный benchmark качества;
- temperature/background GPU load зафиксированы, но не полностью управляются;
- отсутствие detected inversion не устанавливает эквивалентность метрик;
- стоимость не включает CPU, память, охлаждение, PUE и амортизацию.

## 15. Первичные методические источники

- NVIDIA NVML: https://docs.nvidia.com/deploy/nvml-api/latest/
- Ollama API metrics: https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx
- Kalibera & Jones, hierarchical benchmarking: https://kar.kent.ac.uk/33611/
- Efron & Tibshirani, bootstrap: https://doi.org/10.1214/ss/1177013815
- MLPerf wall-power boundary: https://github.com/mlcommons/inference_policies/blob/master/power_measurement.adoc
- Полный индекс чтения: `docs/reading-index.md`.
