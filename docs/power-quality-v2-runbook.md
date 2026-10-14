# Runbook power-quality-v2

> Статус: серия завершена 11 октября 2026 года. Этот документ сохраняет
> воспроизводимый порядок, но повторный запуск для текущей статьи не требуется.

Этот документ задаёт порядок производственных запусков. Runner не меняет
режим питания. Ненулевой exit code означает немедленную остановку серии:
следующий TOML не запускается, артефакты вручную не исправляются.

## Перед каждым сеансом

- ноутбук или ПК подключён к сети;
- закрыты игры, браузеры с аппаратным ускорением, видеоплееры, оверлеи и
  другие GPU-задачи;
- версии драйвера, Ollama и модели совпадают с TOML;
- обе модели установлены заранее; runner ничего не загружает из сети;
- `ollama ps` пуст, GPU остыл ниже порога TOML;
- один блок выполняется целиком, параллельные запуски запрещены.

`doctor` загружает модель, поэтому после него обе модели нужно снова
выгрузить. `run` требует пустой `/api/ps`, 15 секунд измеряет фон GPU и
останавливается при несовпадении среды или зарегистрированной мощности.

## RTX 5060 Laptop: порядок 80 Вт → проверка → 115 Вт

На MAIBENBEN X16C мощность задаётся режимом Control Center:

- Gaming соответствует NVML current/requested 80 Вт;
- Turbo соответствует NVML current/requested 115 Вт;
- Custom и Office не используются, потому что отключают дискретную GPU.

На этом ноутбуке `nvidia-smi -pl` не поддерживает изменение лимита. Не
пытайтесь задавать им 80 или 115 Вт. Перед серией выберите режим вручную и
подтвердите его командой `doctor`.

### Шаблон одного запуска

Подставьте в `$config` очередной TOML из списков ниже.

```powershell
$config = "configs/power-quality-v2/rtx5060/llama32-q4-p80-launch1.toml"
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config $config --json
if ($LASTEXITCODE -ne 0) { throw "doctor failed: $config" }
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config $config
if ($LASTEXITCODE -ne 0) { throw "run failed: $config" }
```

### Этап A — Gaming 80 Вт

Режим Gaming не менять до завершения всех шести запусков:

1. `llama32-q4-p80-launch1.toml`
2. `llama32-q4-p80-launch2.toml`
3. `llama32-q4-p80-launch3.toml`
4. `qwen3-q4-p80-launch1.toml`
5. `qwen3-q4-p80-launch2.toml`
6. `qwen3-q4-p80-launch3.toml`

После этапа A центральный исполнитель проверяет каждый run: статус
`completed`, 60/60 валидных измерений, ожидаемый digest и полное размещение
в GPU, отсутствие повторной загрузки модели, совпадение мощности, пробелы
телеметрии не более 500 мс, положительную энергию, качество, разброс трёх
запусков и выбросы. До этого оператор не переключается на Turbo.

### Этап B — Turbo 115 Вт

Только после явного подтверждения этапа A включите Turbo и сообщите об этом.
`doctor` должен увидеть 115 Вт. Затем выполните:

1. `llama32-q4-p115-launch1.toml`
2. `llama32-q4-p115-launch2.toml`
3. `llama32-q4-p115-launch3.toml`
4. `qwen3-q4-p115-launch1.toml`
5. `qwen3-q4-p115-launch2.toml`
6. `qwen3-q4-p115-launch3.toml`

После серии можно вернуть предпочитаемый пользователем режим. В статье
Gaming/Turbo трактуются как двухточечное сравнение режимов ноутбука: они могут
менять не только предел GPU, но также охлаждение и политику CPU.

## RTX 4060 Ti desktop: автоматизированная серия

Профиль подтвердил диапазон 100–195 Вт и возможность `nvidia-smi -pl` из
административной PowerShell. До измерений зафиксированы четыре уровня: 100,
130, 160 и 195 Вт. Матрица содержит 24 запуска и 1440 измеряемых запросов.

Лев выполнил `docs/lev-rtx4060ti-task.md` по неизменяемой метке
`power-quality-v2-rtx4060ti-code-v2`. Получены 24/24 запуска и 1440/1440
валидных запросов. Более поздняя v3 меняет только обработку stderr команды
остановки Ollama и не требует повтора успешной серии. Производственная команда:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-rtx4060ti.ps1 -Execute
```

Скрипт использует заранее сбалансированное Williams-расписание, проверяет
точный hardware/software profile и хешированный Windows/Python lock, ждёт
чистого состояния между условиями, выполняет `doctor` и `run`, останавливается
при первой ошибке и возвращает default 160 Вт в `finally`. Возврат считается
успешным только после повторного чтения фактических 160 Вт. Ручной обход
файлов по алфавиту запрещён: он изменит зафиксированный порядок и может
смешать уровень мощности с нагревом во времени.

Временная метка `power-quality-v2-rtx4060ti-code-v2` разрешает собрать данные
RTX 4060 Ti до готовности GTX 1080, не выдавая неполную общую кампанию за
финальную. Общая `power-quality-v2-code` будет поставлена только после обоих
профилей.

## GTX 1080 external

Palit GTX 1080 GameRock получает роль `external` и три уровня: 100, 150 и
штатные 200 Вт. Матрица содержит 18 запусков и 1080 измеряемых запросов;
поддерживаемые BIOS границы подтверждены аппаратным preflight как 90–240 Вт.
Уровень 240 Вт не используется: внешняя репликация проверяет снижение
мощности, а не разгон старой карты.

Дима выполнил `docs/dimas-gtx1080-task.md` по метке
`power-quality-v2-gtx1080-code-v3`. Получены 18/18 запусков и 1080/1080
валидных запросов:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-gtx1080.ps1 -Execute
```

Перед первым изменением мощности скрипт требует драйвер 582.66, Ollama
0.35.0, 8192 MiB и фактический профиль default/min/max 200/90/240 Вт. При
отличии BIOS он останавливается до измерений: значения не исправляются на
стенде задним числом, а централизованно выпускается новая метка. После серии
скрипт проверяет точную матрицу и подтверждает возврат штатных 200 Вт.

## Анализ после полных серий

Порядок двух `--primary-host` значим: первым указывается двухуровневый
RTX 5060, вторым — четырёхуровневый RTX 4060 Ti.

```powershell
$runArguments = @()
Get-ChildItem experiments/runs/power-quality-v2 -Directory | ForEach-Object {
    $runArguments += @("--run", $_.FullName)
}
.\.venv\Scripts\python.exe -m llm_energy_bench analyze-power-quality `
  --primary-host maibenben-x16c-rtx5060 `
  --primary-host rtx4060ti-desktop `
  --external-host gtx1080-observation `
  @runArguments `
  --output-dir experiments/studies/power-quality-v2
```

Анализ обязан отклонить неполную матрицу, schema v2, drift
digest/runtime/prompts или смешение ролей.

