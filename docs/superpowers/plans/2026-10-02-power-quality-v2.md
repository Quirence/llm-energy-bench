# Реализация эксперимента power-quality-v2

> **Для исполнителей:** ОБЯЗАТЕЛЬНЫЙ ДОПОЛНИТЕЛЬНЫЙ НАВЫК: выполнять план по задачам через `superpowers:executing-plans` при самостоятельной реализации или `superpowers:subagent-driven-development` при явно выбранной работе с субагентами. Состояние шагов отмечается флажками `- [ ]`.

**Цель:** подготовить `llm-energy-bench` к воспроизводимому второму эксперименту по влиянию power limit на скорость, энергию GPU и точность ответов, проверить его на RTX 5060 Laptop и выпустить метку `power-quality-v2-code` для RTX 4060 Ti и GTX 1080.

**Архитектура:** старый протокол и `paper-dataset-v1` остаются неизменяемыми. Новая конфигурация включает протокол исследования, ожидаемый power limit и пороги среды; runner создаёт schema v3, останавливает запуск при несоответствии среды и лимита, а отдельный модуль `power_quality.py` строит детерминированный анализ только из совместимых v3-прогонов.

**Технологии:** Python 3.12, стандартная библиотека, `httpx`, `nvidia-ml-py`, TOML/JSONL/gzip, `pytest`, `ruff`, Ollama и NVML.

**Спецификация:** `docs/superpowers/specs/2026-10-02-power-quality-v2-design.md`

## Общие ограничения

- Не изменять содержимое `experiments/studies/paper-dataset-v1` и зафиксированный анализ первого исследования.
- Старые конфигурации продолжают создавать schema v2; только `protocol_id = "power-quality-v2"` создаёт schema v3.
- Runtime второго эксперимента — только Ollama; модели — `llama3.2:3b-instruct-q4_K_M` и `qwen3:4b-instruct-2507-q4_K_M` с зафиксированными digest.
- Инструмент не выполняет `nvidia-smi -pl` и не вызывает NVML API изменения мощности.
- Допуск expected/actual power limit равен 1 Вт и явно записывается в конфигурации.
- RTX 5060 Laptop и RTX 4060 Ti имеют по четыре уровня мощности; GTX 1080 — три уровня и роль `external`.
- Каждый condition имеет пять повторений запросов и три независимых запуска.
- Runtime-зависимости не расширяются; построение графиков заменяется детерминированными CSV-кривыми и Markdown-таблицами.
- Новых тестов должно быть не больше двадцати; в ходе задач запускаются только затронутые тесты, полный существующий набор выполняется один раз перед меткой.
- Все пользовательские инструкции и документы для прогонов пишутся по-русски; имена полей и команд остаются техническими идентификаторами.

## Особое внимание при ревью

- Legacy-конфигурация без `[study]` должна сериализоваться и хешироваться так же, как до изменений; это закрепляется тестом Task 1.
- `expect_exact = "16"` не должно принимать `160`, `Ответ: 16` или другой регистр; это закрепляется тестом Task 3.
- Отсутствующее либо меняющееся значение power limit должно останавливать v2, но не ломать старый schema-v2 запуск; это закрепляется тестами Tasks 2–4.
- Нулевая доля правильных ответов не должна приводить к делению на ноль или фиктивному нулю energy/correct; это закрепляется тестом Task 5.
- Отчёт не должен принять неполную матрицу, смешать v2 с `paper-dataset-v1` или объединить GTX 1080 с основными GPU; это закрепляется тестами Task 5.

---

### Task 1: Контракт конфигурации и точных промптов

**Файлы:**

- Изменить: `src/llm_energy_bench/config.py`
- Изменить: `tests/test_config.py`

**Интерфейсы:**

- Потребляет: существующие `ExperimentConfig`, `PromptCase`, `load_config()` и `load_prompts()`.
- Создаёт: `HostRole`, `StudyControls`, `EnvironmentLimits`; поля `ExperimentConfig.study`, `expected_power_limit_watts`, `power_limit_tolerance_watts`, `environment`; поле `PromptCase.expect_exact`.

- [ ] **Шаг 1: написать три целевых теста конфигурации с параметризованными ошибками**

В `tests/test_config.py` определить v2 fixture без дублирования legacy fixture:

```python
POWER_QUALITY_CONFIG = VALID_CONFIG.replace(
    "telemetry_interval_ms = 100\n",
    """telemetry_interval_ms = 100
expected_power_limit_watts = 80.0
power_limit_tolerance_watts = 1.0

[study]
protocol_id = "power-quality-v2"
host_role = "primary"
condition_id = "llama32-q4-p80"
launch_index = 1

[environment]
idle_probe_seconds = 15.0
max_gpu_utilization_p95_percent = 5.0
max_start_temperature_c = 55
max_idle_vram_used_mib = 512.0
""",
)
```

Добавить проверки с такими утверждениями:

```python
def test_power_quality_v2_loads_complete_controls_and_rejects_partial(tmp_path: Path) -> None:
    path = write_config(tmp_path, POWER_QUALITY_CONFIG)
    config = load_config(path)
    assert config.study == StudyControls(
        protocol_id="power-quality-v2",
        host_role=HostRole.PRIMARY,
        condition_id="llama32-q4-p80",
        launch_index=1,
    )
    assert config.expected_power_limit_watts == 80.0
    assert config.power_limit_tolerance_watts == 1.0
    assert config.environment is not None
    broken = POWER_QUALITY_CONFIG.replace("expected_power_limit_watts = 80.0\n", "")
    with pytest.raises(ConfigError, match="expected_power_limit_watts"):
        load_config(write_config(tmp_path, broken))


def test_legacy_contract_keeps_config_fingerprint_and_prompt_shape(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    assert config.study is None
    assert config.expected_power_limit_watts is None
    assert "study" not in config.to_dict()
    assert config.fingerprint() == "db5ae3196c7d6cc6432e21e13933e47f29a2dac04c62ef2fdfc28e4997838ebc"
    prompt = load_prompts(write_prompts(tmp_path, SCORED))[0]
    assert "expect_exact" not in prompt.to_dict()
    assert prompt.to_dict()["expect_contains"] == ["4"]


def test_scored_prompt_accepts_exactly_one_scoring_contract(tmp_path: Path) -> None:
    record = {key: value for key, value in SCORED.items() if key != "expect_contains"}
    prompt = load_prompts(write_prompts(tmp_path, {**record, "expect_exact": "16"}))[0]
    assert prompt.expect_exact == "16"
    assert prompt.expect_contains == ()
```

Также проверить отклонение `launch_index` вне `1..3`, неизвестной `host_role`, неположительного допуска, пустого `expect_exact` и одновременных `expect_exact`/`expect_contains` внутри этих же параметризованных тестов.

- [ ] **Шаг 2: запустить только новые тесты и убедиться, что они падают**

Команда:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -k "power_quality or exact or legacy_config or legacy_prompt" -q
```

Ожидание: тесты падают из-за отсутствующих типов и полей.

- [ ] **Шаг 3: реализовать минимальный строгий контракт**

Добавить типы:

```python
class HostRole(StrEnum):
    PRIMARY = "primary"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class StudyControls:
    protocol_id: str
    host_role: HostRole
    condition_id: str
    launch_index: int

    def to_dict(self) -> dict[str, str | int]: ...


@dataclass(frozen=True, slots=True)
class EnvironmentLimits:
    idle_probe_seconds: float
    max_gpu_utilization_p95_percent: float
    max_start_temperature_c: int
    max_idle_vram_used_mib: float

    def to_dict(self) -> dict[str, int | float]: ...
```

Расширить разрешённые поля:

```python
"study": {"protocol_id", "host_role", "condition_id", "launch_index"},
"gpu": {
    "index", "telemetry_interval_ms", "expected_power_limit_watts",
    "power_limit_tolerance_watts",
},
"environment": {
    "idle_probe_seconds", "max_gpu_utilization_p95_percent",
    "max_start_temperature_c", "max_idle_vram_used_mib",
},
```

Для `power-quality-v2` требовать `[study]`, оба power-limit поля и все поля
`[environment]`. Для старых конфигураций эти поля должны отсутствовать либо
быть `None`. `ExperimentConfig.to_dict()` добавляет `study`, `environment` и
power-limit controls только для v2, чтобы legacy fingerprint не изменился.

В `PromptCase` добавить `expect_exact: str | None = None`. Для `scored`
разрешить ровно один способ проверки. `to_dict()` добавляет `expect_exact`
только при непустом значении, сохраняя старую сериализацию.

- [ ] **Шаг 4: выполнить тесты конфигурации**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -q
.\.venv\Scripts\python.exe -m ruff check src/llm_energy_bench/config.py tests/test_config.py
```

Ожидание: весь `test_config.py` проходит, ruff не сообщает ошибок.

- [ ] **Шаг 5: зафиксировать контракт**

```powershell
git add src/llm_energy_bench/config.py tests/test_config.py
git commit -m "feat: define power quality v2 controls"
```

---

### Task 2: NVML-профиль мощности и проверка простоя

**Файлы:**

- Изменить: `src/llm_energy_bench/nvml.py`
- Создать: `src/llm_energy_bench/environment.py`
- Изменить: `tests/fake_nvml.py`
- Изменить: `tests/test_nvml.py`
- Создать: `tests/test_environment.py`

**Интерфейсы:**

- Потребляет: `EnvironmentLimits`, `GpuCapabilities`, `NvmlSampler`, `TelemetrySample`.
- Создаёт: дополнительные поля power-limit профиля; `EnvironmentBaseline`; `ensure_expected_power_limit()`; `summarize_environment_samples()`; `capture_idle_baseline()`; `request_power_limit_problems()`.

- [ ] **Шаг 1: написать тесты NVML-профиля**

```python
@pytest.mark.parametrize("supported", [True, False])
def test_probe_reports_power_limit_profile_or_explicit_nulls(supported: bool) -> None:
    enabled = FULL_SUPPORT if supported else tuple(
        field for field in FULL_SUPPORT if field not in {
            "power_limit_constraints_mw", "power_limit_default_mw"
        }
    )
    caps = NvmlSampler(binding=FakeNvml(supported=enabled, power_limit_mw=80_000)).probe(0)
    if supported:
        assert caps.power_limit_watts == pytest.approx(80.0)
        assert caps.power_limit_default_watts == pytest.approx(80.0)
        assert caps.power_limit_min_watts == pytest.approx(5.0)
        assert caps.power_limit_max_watts == pytest.approx(115.0)
    else:
        assert caps.power_limit_min_watts is None
        assert caps.power_limit_max_watts is None
        assert caps.power_limit_default_watts is None
```

Расширить `NvmlBinding` и `PynvmlBinding` методами:

```python
def power_limit_constraints_mw(self, handle: Any) -> tuple[int, int]: ...
def power_limit_default_mw(self, handle: Any) -> int: ...
```

Они используют `nvmlDeviceGetPowerManagementLimitConstraints` и
`nvmlDeviceGetPowerManagementDefaultLimit`. Методов изменения лимита в binding
не добавлять. В `GpuCapabilities` поля `power_limit_default_watts`,
`power_limit_min_watts` и `power_limit_max_watts` добавляются в конце списка
обязательных полей со значением по умолчанию `None`, чтобы существующие fake
capability records не требовали механического переписывания.

В `FakeNvml` добавить `power_limit_mw=60_000`,
`power_limit_default_mw=80_000`, `power_limit_min_mw=5_000` и
`power_limit_max_mw=115_000`; `enforced_power_limit_mw()` перестаёт возвращать
literal и читает поле. Новые имена входят в `FULL_SUPPORT`.

- [ ] **Шаг 2: написать тесты защитных функций среды**

В `tests/test_environment.py` создать компактный helper
`environment_sample(timestamp, *, utilization, temperature, power, vram,
power_limit) -> TelemetrySample` с постоянными request ID `environment-preflight`,
UTC-временем и заполненными instant/legacy power. Из него собрать:

```python
BUSY_SAMPLES = (
    environment_sample(0.0, utilization=90, temperature=60, power=20.0, vram=600 * 1024**2, power_limit=80.0),
    environment_sample(1.0, utilization=95, temperature=61, power=25.0, vram=620 * 1024**2, power_limit=80.0),
)
POWER_CHANGED = (
    environment_sample(0.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=80.0),
    environment_sample(1.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=60.0),
)
POWER_MISSING = (
    environment_sample(0.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=None),
    environment_sample(1.0, utilization=0, temperature=40, power=10.0, vram=100, power_limit=None),
)
```

```python
def test_expected_power_limit_mismatch_fails_closed() -> None:
    with pytest.raises(MeasurementEnvironmentError, match="80.0.*60.0"):
        ensure_expected_power_limit(observed_watts=60.0, expected_watts=80.0, tolerance_watts=1.0)


def test_idle_baseline_rejects_busy_or_hot_gpu() -> None:
    baseline = summarize_environment_samples(BUSY_SAMPLES)
    problems = baseline.problems(EnvironmentLimits(15.0, 5.0, 55, 512.0))
    assert "gpu_utilization_p95" in problems
    assert "start_temperature" in problems


def test_request_power_limit_detects_change_and_missing_samples() -> None:
    assert request_power_limit_problems(POWER_CHANGED, 80.0, 1.0) == (
        "power_limit_mismatch", "power_limit_changed"
    )
    assert request_power_limit_problems(POWER_MISSING, 80.0, 1.0) == ("power_limit_missing",)
```

- [ ] **Шаг 3: убедиться, что новые тесты падают**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvml.py -k "power_limit_profile" -q
.\.venv\Scripts\python.exe -m pytest tests/test_environment.py -q
```

- [ ] **Шаг 4: реализовать профиль и baseline без новых зависимостей**

В `environment.py` создать:

```python
class MeasurementEnvironmentError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EnvironmentBaseline:
    duration_seconds: float
    sample_count: int
    gpu_utilization_mean_percent: float
    gpu_utilization_median_percent: float
    gpu_utilization_p95_percent: float
    power_mean_watts: float
    power_p95_watts: float
    temperature_start_c: int
    temperature_peak_c: int
    vram_used_peak_bytes: int

    def problems(self, limits: EnvironmentLimits) -> tuple[str, ...]: ...
    def to_dict(self) -> dict[str, int | float | list[str]]: ...


def ensure_expected_power_limit(
    observed_watts: float | None,
    expected_watts: float,
    tolerance_watts: float,
) -> None: ...


def capture_idle_baseline(
    sampler: NvmlSampler,
    limits: EnvironmentLimits,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> EnvironmentBaseline: ...


def summarize_environment_samples(
    samples: tuple[TelemetrySample, ...],
) -> EnvironmentBaseline: ...


def request_power_limit_problems(
    samples: tuple[TelemetrySample, ...],
    expected_watts: float,
    tolerance_watts: float,
) -> tuple[str, ...]: ...
```

`capture_idle_baseline()` использует обычные `sampler.start()`/`stop()`,
требует минимум два отсчёта и выбирает instantaneous power, затем legacy power.
Для v2 отсутствие загрузки, температуры, VRAM или power samples является
ошибкой, а не нулём.

- [ ] **Шаг 5: выполнить узкий набор тестов**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvml.py tests/test_environment.py -q
.\.venv\Scripts\python.exe -m ruff check src/llm_energy_bench/nvml.py src/llm_energy_bench/environment.py tests/fake_nvml.py tests/test_nvml.py tests/test_environment.py
```

- [ ] **Шаг 6: зафиксировать NVML и environment**

```powershell
git add src/llm_energy_bench/nvml.py src/llm_energy_bench/environment.py tests/fake_nvml.py tests/test_nvml.py tests/test_environment.py
git commit -m "feat: validate GPU power and idle state"
```

---

### Task 3: Точная оценка ответа и стабильность power limit запроса

**Файлы:**

- Изменить: `src/llm_energy_bench/runner.py`
- Изменить: `tests/test_runner.py`

**Интерфейсы:**

- Потребляет: `PromptCase.expect_exact`, `request_power_limit_problems()`.
- Создаёт: `score_response(prompt, text) -> float | None`; новые причины недействительности `power_limit_missing`, `power_limit_mismatch`, `power_limit_changed`.

- [ ] **Шаг 1: написать четыре проверки в двух параметризованных тестах**

```python
@pytest.mark.parametrize(
    ("text", "score"),
    [("16", 1.0), (" 16\n", 1.0), ("160", 0.0), ("Ответ: 16", 0.0)],
)
def test_exact_scoring_is_strict(text: str, score: float) -> None:
    assert score_response(exact_prompt("16"), text) == score


def test_request_metrics_reject_power_limit_drift() -> None:
    changed = (
        sample("request-1", 0.0, energy_j=10.0, instant_w=10.0, power_limit_watts=80.0),
        sample("request-1", 1.0, energy_j=20.0, instant_w=10.0, power_limit_watts=60.0),
    )
    metrics = derive_request_metrics(
        result(text="16"), changed, capabilities(), exact_prompt("16"),
        repetition=0, expected_power_limit_watts=80.0,
        power_limit_tolerance_watts=1.0,
    )
    assert metrics.valid is False
    assert "power_limit_changed" in metrics.invalid_reasons
```

Существующий тест `expect_contains` должен продолжить проходить без изменения
семантики старых данных. Тестовый helper `result()` получает keyword
`text: str = "4"`, helper `sample()` — keyword
`power_limit_watts: float | None = 80.0`, а `exact_prompt(expected)` возвращает
`PromptCase("exact", PromptCategory.SCORED, "answer", expect_exact=expected)`.

- [ ] **Шаг 2: запустить тесты до реализации**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runner.py -k "exact_scoring or power_limit_drift or efficiency_throughput" -q
```

- [ ] **Шаг 3: реализовать scorer и power checks в derive_request_metrics**

Сигнатура расширяется только keyword-параметрами:

```python
def derive_request_metrics(
    result: InferenceResult,
    samples: tuple[TelemetrySample, ...],
    capabilities: GpuCapabilities,
    prompt: PromptCase,
    *,
    repetition: int,
    template_cache_baseline_tokens: int = 0,
    tariff_per_kwh: float | None = None,
    currency: str | None = None,
    expected_power_limit_watts: float | None = None,
    power_limit_tolerance_watts: float | None = None,
) -> RequestMetrics: ...
```

`score_response()` сначала обрабатывает `expect_exact` через `text.strip() ==
expected`, иначе использует прежний `all(expected in text ...)`. Power-limit
причины добавляются только когда оба новых параметра заданы, поэтому legacy
поведение не меняется.

- [ ] **Шаг 4: проверить runner-модуль**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runner.py -q
.\.venv\Scripts\python.exe -m ruff check src/llm_energy_bench/runner.py tests/test_runner.py
```

- [ ] **Шаг 5: зафиксировать метрики запроса**

```powershell
git add src/llm_energy_bench/runner.py tests/test_runner.py
git commit -m "feat: score exact answers and enforce request power"
```

---

### Task 4: Оркестрация schema v3 и независимая валидация

**Файлы:**

- Изменить: `src/llm_energy_bench/runner.py`
- Изменить: `src/llm_energy_bench/results.py`
- Изменить: `src/llm_energy_bench/cli.py`
- Изменить: `tests/test_runner.py`
- Изменить: `tests/test_results.py`
- Изменить: `tests/test_report.py`

**Интерфейсы:**

- Потребляет: Task 1–3 controls и helpers, `OllamaClient.running_models()`.
- Создаёт: schema-v3 manifest с `study`, `environment_baseline` и power profile; `_validate_schema_v3()`; расширенный `doctor`.

Тестовые helpers в этой задаче имеют фиксированные контракты:

```python
def v2_config(tmp_path: Path) -> ExperimentConfig:
    """One-model, one-prompt, one-repetition v2 config with output under tmp_path."""


class ResidentClient(FakeClient):
    def running_models(self) -> tuple[RunningModel, ...]:
        return (self.preload(MODEL, options={"num_ctx": 4096, "num_gpu": 999}),)


class BusySampler(FakeSampler):
    """Return BUSY_SAMPLES for the first environment-preflight start/stop pair."""


def schema_v3_run(
    tmp_path: Path,
    *,
    telemetry_power_limits: tuple[float | None, ...] = (80.0, 80.0),
) -> Path:
    """Extend the existing schema_v2_run fixture with valid v3 study/baseline controls."""


def rewrite_manifest(run_dir: Path, *, schema_version: int) -> None:
    """Rewrite schema_version with write_json, leaving every other field byte-equivalent."""
```

- [ ] **Шаг 1: написать интеграционные проверки нового preflight**

```python
def test_v2_run_rejects_resident_model_before_idle_probe(tmp_path: Path) -> None:
    with pytest.raises(RunnerPreflightError, match="ollama stop"):
        run_experiment(v2_config(tmp_path), client_factory=ResidentClient, sampler_factory=FakeSampler)


def test_v2_run_preserves_failed_environment_manifest(tmp_path: Path) -> None:
    with pytest.raises(MeasurementEnvironmentError):
        run_experiment(v2_config(tmp_path), client_factory=FakeClient, sampler_factory=BusySampler)
    manifest = json.loads(next(tmp_path.glob("**/manifest.json")).read_text())
    assert manifest["schema_version"] == 3
    assert manifest["status"] == "failed"
    assert manifest["environment_baseline"]["problems"]


def test_legacy_run_still_writes_schema_v2(tmp_path: Path) -> None:
    run_dir = run_experiment(make_config(tmp_path))
    assert json.loads((run_dir / "manifest.json").read_text())["schema_version"] == 2
```

Fake client получает `running_models() -> ()`; fake sampler возвращает
отдельные idle samples до request samples.

- [ ] **Шаг 2: написать проверки независимого schema-v3 validator**

```python
def test_schema_v3_rejects_changed_power_limit_even_if_output_claims_valid(tmp_path: Path) -> None:
    run_dir = schema_v3_run(tmp_path, telemetry_power_limits=(80.0, 60.0))
    assert validate_run(run_dir).ok is False
    assert any("power limit" in item for item in validate_run(run_dir).errors)


def test_schema_v3_cannot_be_relabelled_schema_v2(tmp_path: Path) -> None:
    run_dir = schema_v3_run(tmp_path)
    rewrite_manifest(run_dir, schema_version=2)
    assert validate_run(run_dir).ok is False
```

- [ ] **Шаг 3: запустить новые интеграционные тесты и подтвердить падение**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runner.py tests/test_results.py -k "v2_run or schema_v3 or legacy_run" -q
```

- [ ] **Шаг 4: перестроить только v2-путь run_experiment**

Для v2 порядок действий фиксируется так:

1. Проверить runtime/version, установленные digest и доступность NVML-полей,
   но ещё не отклонять несовпадающее числовое значение power limit.
2. Вызвать `client.running_models()` и отказать, если список непустой.
3. Создать run directory, resolved config и начальный schema-v3 manifest с
   пустым `models` и наблюдаемым аппаратным power profile.
4. Внутри существующего блока сохранения ошибки проверить expected power
   limit, выполнить idle baseline и записать проблемы в manifest.
5. Повторно проверить текущий power limit после baseline.
6. Preload модели, проверить digest и полное GPU placement, заменить пустой
   `models` проверенными `RunningModel` records и обновить manifest.
7. Выполнить warmups и measured requests с power-limit параметрами Task 3.
8. Повторно вызвать `sampler.probe()` после серии и проверить лимит.

Legacy-путь сохраняет нынешний порядок и schema v2. В `_initial_manifest()`
использовать:

```python
"schema_version": 3 if config.study is not None else 2,
"study": None if config.study is None else config.study.to_dict(),
"environment_baseline": None,
```

Resolved TOML v3 содержит `[study]`, `[gpu]` и `[environment]` с точными
фактическими значениями конфигурации.

- [ ] **Шаг 5: реализовать schema-v3 validator без ослабления v2**

`_validate_completed_schema()` вызывает новый обработчик:

```python
elif schema == 3:
    _validate_schema_v3(run_dir, manifest, counts, checksums, errors)
```

`_validate_schema_v3()` повторно применяет общие проверки schema v2, затем
независимо проверяет protocol, host role, launch index, baseline, expected
power limit и каждый сырой telemetry sample. Значение `study.protocol_id`
должно быть ровно `power-quality-v2`. Обработчик schema v2, в свою очередь,
отклоняет ненулевые `study` и `environment_baseline`, поэтому простое изменение
цифры версии не позволяет выдать v3-run за старый формат.

- [ ] **Шаг 6: расширить doctor аппаратным профилем**

JSON и текстовый `doctor` показывают current/default/min/max power limit.
Для v2 `report["ok"]` дополнительно требует доступного текущего лимита и его
совпадения с expected. `doctor` может preload модели для проверки placement,
но текстовый вывод напоминает выполнить обе команды
`ollama stop llama3.2:3b-instruct-q4_K_M` и
`ollama stop qwen3:4b-instruct-2507-q4_K_M` перед `run`.

- [ ] **Шаг 7: выполнить затронутые тестовые модули**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runner.py tests/test_results.py tests/test_report.py tests/test_cli.py -q
.\.venv\Scripts\python.exe -m ruff check src/llm_energy_bench/runner.py src/llm_energy_bench/results.py src/llm_energy_bench/cli.py tests/test_runner.py tests/test_results.py tests/test_report.py
```

- [ ] **Шаг 8: зафиксировать schema v3**

```powershell
git add src/llm_energy_bench/runner.py src/llm_energy_bench/results.py src/llm_energy_bench/cli.py tests/test_runner.py tests/test_results.py tests/test_report.py tests/test_cli.py
git commit -m "feat: record and validate power quality runs"
```

---

### Task 5: Отдельный детерминированный анализ power-quality-v2

**Файлы:**

- Создать: `src/llm_energy_bench/power_quality.py`
- Изменить: `src/llm_energy_bench/cli.py`
- Создать: `tests/test_power_quality.py`
- Изменить: `tests/test_cli.py`

**Интерфейсы:**

- Потребляет: только validated schema-v3 run directories.
- Создаёт: `analyze_power_quality()` и `write_power_quality_analysis()`; CLI `analyze-power-quality`.

Тестовый builder имеет сигнатуру:

```python
def synthetic_v2_matrix(
    tmp_path: Path,
    *,
    omit: tuple[str, str, float, int] | None = None,
) -> tuple[Path, ...]:
    """Create two primary 2x4x3 grids and one external 2x3x3 grid of valid v3 runs."""


def samples(
    *,
    energy: tuple[float, ...] = (10.0, 20.0),
    latency: tuple[float, ...] = (1.0, 2.0),
    correct: tuple[float, ...] = (1.0, 0.0),
) -> tuple[PowerQualitySample, ...]: ...
```

`FAST_HIGH_ENERGY`, `SLOW_LOW_ENERGY` и `DOMINATED` являются тремя
`ConditionAggregate` fixtures: первый максимизирует скорость, второй
минимизирует энергию без потери качества, третий хуже второго по всем трём
осям.

- [ ] **Шаг 1: написать тест несовместимого и неполного набора**

```python
def test_analysis_rejects_legacy_and_incomplete_matrix(tmp_path: Path) -> None:
    with pytest.raises(PowerQualityError, match="schema_version 3"):
        analyze_power_quality((schema_v2_run(tmp_path),), ("rtx5060", "rtx4060ti"), "gtx1080")

    runs = synthetic_v2_matrix(tmp_path, omit=("rtx4060ti", "qwen3", 120.0, 3))
    with pytest.raises(PowerQualityError, match="incomplete matrix"):
        analyze_power_quality(runs, ("rtx5060", "rtx4060ti"), "gtx1080")
```

Матрица считается полной, когда для каждого primary host присутствуют две
модели × четыре разных power limit × launch indices `{1,2,3}`, а для external
host — две модели × три лимита × те же три launch indices. Каждый run содержит
одну модель.

- [ ] **Шаг 2: написать тесты формул, нулевого качества и разделения ролей**

```python
def test_energy_per_correct_uses_sums_and_zero_is_null() -> None:
    row = aggregate_condition(samples(energy=(10.0, 20.0), latency=(1.0, 2.0), correct=(1.0, 0.0)))
    assert row.energy_per_correct_joules == pytest.approx(30.0)
    assert row.latency_per_correct_seconds == pytest.approx(3.0)
    assert aggregate_condition(samples(correct=(0.0, 0.0))).energy_per_correct_joules is None


def test_external_gpu_is_not_pooled_with_primary_hosts(tmp_path: Path) -> None:
    result = analyze_power_quality(synthetic_v2_matrix(tmp_path), ("rtx5060", "rtx4060ti"), "gtx1080")
    assert {row.host_role for row in result.rows} == {"primary", "external"}
    assert all(row.host_id != "gtx1080" for row in result.primary_comparisons)
```

- [ ] **Шаг 3: написать тест компромисса и детерминированного вывода**

```python
def test_tradeoff_frontier_distinguishes_inversion_and_no_inversion() -> None:
    frontier = mark_frontier((FAST_HIGH_ENERGY, SLOW_LOW_ENERGY, DOMINATED))
    assert frontier == (FAST_HIGH_ENERGY, SLOW_LOW_ENERGY)


def test_analysis_artifacts_are_byte_deterministic(tmp_path: Path) -> None:
    analysis = analyze_power_quality(synthetic_v2_matrix(tmp_path), ("rtx5060", "rtx4060ti"), "gtx1080")
    first = write_power_quality_analysis(analysis, tmp_path / "first")
    second = write_power_quality_analysis(analysis, tmp_path / "second")
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]
```

- [ ] **Шаг 4: запустить тесты и подтвердить отсутствие модуля**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_power_quality.py tests/test_cli.py -k "power_quality or correct or frontier" -q
```

- [ ] **Шаг 5: реализовать анализ с отношениями сумм**

Публичные интерфейсы:

```python
class PowerQualityError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PowerQualitySample:
    host_id: str
    host_role: HostRole
    model: str
    power_limit_watts: float
    workload: PromptCategory
    launch_index: int
    output_tokens: int
    eval_duration_seconds: float
    energy_joules: float
    latency_seconds: float
    quality_score: float | None


@dataclass(frozen=True, slots=True)
class ConditionAggregate:
    host_id: str
    host_role: HostRole
    model: str
    power_limit_watts: float
    workload: PromptCategory
    tokens_per_second: float
    tokens_per_joule: float
    median_energy_per_request_joules: float
    quality_score: float | None
    energy_per_correct_joules: float | None
    latency_per_correct_seconds: float | None
    throughput_change_from_baseline: float | None = None
    energy_change_from_baseline: float | None = None
    on_tradeoff_frontier: bool = False


@dataclass(frozen=True, slots=True)
class PowerQualityAnalysis:
    rows: tuple[ConditionAggregate, ...]
    primary_comparisons: tuple[ConditionAggregate, ...]
    run_rows: tuple[dict[str, Any], ...]


def aggregate_condition(samples: tuple[PowerQualitySample, ...]) -> ConditionAggregate: ...


def mark_frontier(rows: tuple[ConditionAggregate, ...]) -> tuple[ConditionAggregate, ...]: ...


def analyze_power_quality(
    run_dirs: tuple[Path, ...],
    primary_hosts: tuple[str, str],
    external_host: str,
) -> PowerQualityAnalysis: ...


def write_power_quality_analysis(
    analysis: PowerQualityAnalysis,
    output_dir: Path,
) -> tuple[Path, Path, Path]: ...
```

Три результата называются `power-quality-runs.csv`,
`power-quality-summary.csv` и `power-quality-report.md`. Summary группируется
по host/model/power/workload, использует суммы для tok/s, tok/J,
energy/correct и latency/correct. Базой относительных изменений является
максимальный из проверенных лимитов конкретного host. Pareto-флаг вычисляется
отдельно внутри host/workload; внешняя GTX 1080 не входит в primary comparison.

- [ ] **Шаг 6: добавить CLI без изменения команды первого анализа**

```text
$runArguments = @()
Get-ChildItem experiments/runs/power-quality-v2 -Directory | ForEach-Object {
    $runArguments += @("--run", $_.FullName)
}
.\.venv\Scripts\python.exe -m llm_energy_bench analyze-power-quality `
  --primary-host rtx5060-laptop `
  --primary-host rtx4060ti `
  --external-host gtx1080 `
  @runArguments `
  --output-dir experiments/studies/power-quality-v2
```

Команда `analyze` остаётся привязана к `paper-dataset-v1` и не импортирует
новый модуль.

- [ ] **Шаг 7: проверить новый анализ**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_power_quality.py tests/test_cli.py -q
.\.venv\Scripts\python.exe -m ruff check src/llm_energy_bench/power_quality.py src/llm_energy_bench/cli.py tests/test_power_quality.py tests/test_cli.py
```

- [ ] **Шаг 8: зафиксировать анализ**

```powershell
git add src/llm_energy_bench/power_quality.py src/llm_energy_bench/cli.py tests/test_power_quality.py tests/test_cli.py
git commit -m "feat: analyze power quality response curves"
```

---

### Task 6: Набор запросов, аппаратные профили и инструкции коллегам

**Файлы:**

- Создать: `prompts/power-quality-v2.jsonl`
- Создать: `configs/power-quality-v2/README.md`
- Создать после профилирования: `configs/power-quality-v2/rtx5060/*.toml`
- Создать после получения профиля Льва: `configs/power-quality-v2/rtx4060ti/*.toml`
- Создать после получения профиля Димы: `configs/power-quality-v2/gtx1080/*.toml`
- Создать: `docs/power-quality-v2-runbook.md`
- Создать: `docs/lev-rtx4060ti-task.md`
- Создать: `docs/dimas-gtx1080-task.md`
- Изменить: `STATUS.md`
- Изменить: `docs/experiment-log.md`
- Изменить: `tests/test_config.py`

**Интерфейсы:**

- Потребляет: полностью реализованный schema-v3 runner и фактические hardware profiles.
- Создаёт: неизменяемый prompt set, точные host configs и исполнимые русские инструкции.

- [ ] **Шаг 1: создать и проверить фиксированный набор из 12 запросов**

Состав:

- `decode-01..02`: короткий вход с требованием длинного продолжения до лимита;
- `prefill-01..02`: длинный синтетический вход и короткий ответ;
- `exact-01..08`: арифметика, логика, извлечение значения и следование формату,
  каждый с `expect_exact`.

Все тексты создаются внутри проекта, не копируются из закрытых наборов и не
используются как общий benchmark качества. Документация называет результат
«точностью фиксированных задач», а не общей интеллектуальностью модели.

Тест закрепляет:

```python
def test_power_quality_prompt_set_is_frozen() -> None:
    prompts = load_prompts(ROOT / "prompts/power-quality-v2.jsonl")
    assert len(prompts) == 12
    assert Counter(item.category for item in prompts) == {
        PromptCategory.SHORT: 2,
        PromptCategory.LONG: 2,
        PromptCategory.SCORED: 8,
    }
    assert all(item.expect_exact for item in prompts if item.is_scored)
```

После создания файла отдельной командой вывести
`prompts_fingerprint(load_prompts(Path("prompts/power-quality-v2.jsonl")))` и
добавить к этому же тесту сравнение с напечатанной 64-символьной строкой.
Коммит не создаётся, пока буквальное значение не записано в тест; изменение
prompts после этого намеренно ломает проверку.

- [ ] **Шаг 2: выполнить локальный hardware profile RTX 5060**

```powershell
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/pilot-rtx5060.toml --json
nvidia-smi -q -d POWER,TEMPERATURE,MEMORY
ollama ps
```

Сохранить sanitized JSON и выбранные current/default/min/max значения в
`configs/power-quality-v2/README.md`. После `doctor` выполнить:

```powershell
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
```

- [ ] **Шаг 3: зафиксировать уровни RTX 5060 до измерений**

Выбрать четыре целых поддерживаемых значения в пределах профиля: штатный
уровень первым, ещё три монотонно меньших уровня с достаточным интервалом.
Перед коммитом выполнить по одному короткому безопасному probe каждого лимита
через `nvidia-smi -pl`, проверить фактическое значение через `doctor`, затем
вернуть штатные 80 Вт.

Для каждой комбинации `2 модели × 4 лимита × 3 launch` создать один TOML с
одной моделью. Имена имеют форму
`llama32-q4-p80-launch1.toml`; остальные имена строятся тем же образом из
фактически утверждённых watts и launch `1`, `2`, `3`; всего 24 файла.

- [ ] **Шаг 4: подготовить точные задания на аппаратное профилирование**

Оба документа коллег содержат:

```powershell
git fetch --tags origin
git checkout power-quality-v2-code
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/pilot-rtx4060ti.toml --json
nvidia-smi -q -d POWER,TEMPERATURE,MEMORY
ollama ps
```

В документе Димы первая команда использует
`configs/pilot-gtx1080-observation.toml`; остальные команды совпадают.

До выпуска метки коллеги присылают только sanitized profile. После профиля
центрально фиксируются 24 конфигурации RTX 4060 Ti и 18 конфигураций GTX 1080.
Коллеги не редактируют код, prompts или TOML.

- [ ] **Шаг 5: написать runbook производственного запуска**

Для каждого config порядок одинаков:

Например, локальный файл `llama32-q4-p80-launch1.toml` получает дословный
блок:

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch1.toml
```

После аппаратного профиля runbook перечисляет такой же дословный блок для
каждого committed config, уже с его фактическим лимитом и путём; оператор не
подставляет значения вручную.

Runbook требует питание от сети, закрытые GPU-приложения и оверлеи, паузу до
пороговой температуры, неизменный драйвер/Ollama и немедленную остановку при
exit code, отличном от нуля. В конце оператор возвращает штатный power limit.

- [ ] **Шаг 6: проверить shipped prompts/configs**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -k "power_quality_prompt or shipped" -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

- [ ] **Шаг 7: зафиксировать протокол запуска**

```powershell
git add prompts/power-quality-v2.jsonl configs/power-quality-v2 docs/power-quality-v2-runbook.md docs/lev-rtx4060ti-task.md docs/dimas-gtx1080-task.md STATUS.md docs/experiment-log.md tests/test_config.py
git commit -m "docs: freeze power quality v2 campaign"
```

---

### Task 7: Локальная аппаратная приёмка и выпуск метки

**Файлы:**

- Добавить: каталоги технических acceptance runs под `experiments/runs/power-quality-v2-acceptance/`
- Изменить: `docs/experiment-log.md`
- Изменить: `STATUS.md`

**Интерфейсы:**

- Потребляет: код Tasks 1–6 и окончательные host profiles.
- Создаёт: проверенную общую базу и Git tag `power-quality-v2-code`.

- [ ] **Шаг 1: выполнить один полный регрессионный прогон тестов**

Это единственный обязательный запуск всего существующего набора перед меткой:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Ожидание: все прежние и не более двадцати новых тестов проходят.

- [ ] **Шаг 2: выполнить 80-ваттный smoke-run обеих моделей**

Использовать по одному acceptance config с 12 prompts × 1 repetition, а не
производственные пять повторений. Проверить schema v3, полный GPU placement,
положительную энергию, точный digest, 100% valid requests и отсутствие
power-limit/environment violations.

- [ ] **Шаг 3: повторить smoke-run и сравнить воспроизводимость**

Сопоставить median tok/s, tok/J и energy/request по model/workload. Различия
фиксируются в журнале; пороги среды корректируются только до начала
производственных запусков и затем замораживаются.

- [ ] **Шаг 4: проверить один пониженный уровень и намеренный отказ**

Выполнить acceptance run на ближайшем пониженном уровне. Затем при фактических
80 Вт запустить config, ожидающий другое значение: процесс обязан завершиться
с exit code 3 до первого measured request и оставить auditable failed manifest.
Вернуть 80 Вт и подтвердить его через `nvidia-smi`.

- [ ] **Шаг 5: проверить детерминированность анализа на синтетической матрице**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_power_quality.py::test_analysis_artifacts_are_byte_deterministic -q
```

Для реальных acceptance runs создать технический отчёт только если они
образуют полную acceptance-матрицу; неполный набор команда обязана отклонить.

- [ ] **Шаг 6: провести финальное ревью diff и документов**

```powershell
git status --short
git diff origin/main...HEAD --check
git log --oneline origin/main..HEAD
```

Убедиться, что в diff нет изменений frozen dataset, приватных путей, raw GPU
UUID, токенов и результатов незаявленных производственных запусков.

- [ ] **Шаг 7: зафиксировать приёмку**

```powershell
git add experiments/runs/power-quality-v2 docs/experiment-log.md STATUS.md
git commit -m "test: accept power quality v2 on rtx5060"
git push origin HEAD
```

- [ ] **Шаг 8: после профилей коллег создать и опубликовать метку**

Условие шага: committed configs содержат фактические профили RTX 4060 Ti и
GTX 1080, ветка интегрирована в `main`, CI зелёный.

```powershell
git checkout main
git pull --ff-only origin main
git tag -a power-quality-v2-code -m "Freeze code and protocol for power-quality-v2"
git push origin power-quality-v2-code
```

После метки Лев и Дима выполняют только свои русские runbooks и коммитят
каталоги результатов вместе с одной записью `docs/experiment-log.md`.
