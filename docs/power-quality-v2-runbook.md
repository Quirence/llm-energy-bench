# Runbook power-quality-v2

Этот документ задаёт порядок производственных запусков. Он не меняет power limit автоматически: оператор выполняет каждую команду явно из PowerShell от имени администратора. Ненулевой exit code означает немедленную остановку серии; не переходите к следующей команде и не исправляйте артефакты вручную.

## Перед каждым сеансом

- ноутбук или ПК подключён к сети, режим питания ОС не меняется между запусками;
- закрыты игры, браузеры с аппаратным ускорением, видеоплееры, оверлеи, wallpaper renderer и другие GPU-задачи;
- версии драйвера, Ollama и модели совпадают с TOML;
- `git status --short` пуст, `git describe --tags --exact-match` выводит `power-quality-v2-code`;
- обе модели установлены заранее; runner ничего не загружает из сети;
- GPU остыл ниже порога TOML; `ollama ps` пуст;
- один блок выполняется целиком, параллельные запуски запрещены.

`doctor` загружает проверяемую модель, поэтому после него обе модели обязательно выгружаются повторно. Сам `run` перед измерением проверяет пустой `/api/ps`, 15 секунд измеряет фон GPU и прекращает работу при несовпадении среды или power limit.

## RTX 5060 Laptop — 24 зафиксированных условия

На этом стенде используются уровни 80, 65, 50 и 35 Вт. До основной серии все четыре значения должны быть подтверждены в административной PowerShell. Если `nvidia-smi -pl` возвращает `Insufficient Permissions`, производственные запуски начинать нельзя.

### Llama 3.2 Q4, 80 Вт, запуск 1

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch1.toml
```

### Llama 3.2 Q4, 80 Вт, запуск 2

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch2.toml
```

### Llama 3.2 Q4, 80 Вт, запуск 3

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p80-launch3.toml
```

### Llama 3.2 Q4, 65 Вт, запуск 1

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch1.toml
```

### Llama 3.2 Q4, 65 Вт, запуск 2

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch2.toml
```

### Llama 3.2 Q4, 65 Вт, запуск 3

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p65-launch3.toml
```

### Llama 3.2 Q4, 50 Вт, запуск 1

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch1.toml
```

### Llama 3.2 Q4, 50 Вт, запуск 2

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch2.toml
```

### Llama 3.2 Q4, 50 Вт, запуск 3

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p50-launch3.toml
```

### Llama 3.2 Q4, 35 Вт, запуск 1

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch1.toml
```

### Llama 3.2 Q4, 35 Вт, запуск 2

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch2.toml
```

### Llama 3.2 Q4, 35 Вт, запуск 3

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/llama32-q4-p35-launch3.toml
```

### Qwen3 4B Q4, 80 Вт, запуск 1

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch1.toml
```

### Qwen3 4B Q4, 80 Вт, запуск 2

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch2.toml
```

### Qwen3 4B Q4, 80 Вт, запуск 3

```powershell
nvidia-smi -pl 80
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p80-launch3.toml
```

### Qwen3 4B Q4, 65 Вт, запуск 1

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch1.toml
```

### Qwen3 4B Q4, 65 Вт, запуск 2

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch2.toml
```

### Qwen3 4B Q4, 65 Вт, запуск 3

```powershell
nvidia-smi -pl 65
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p65-launch3.toml
```

### Qwen3 4B Q4, 50 Вт, запуск 1

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch1.toml
```

### Qwen3 4B Q4, 50 Вт, запуск 2

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch2.toml
```

### Qwen3 4B Q4, 50 Вт, запуск 3

```powershell
nvidia-smi -pl 50
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p50-launch3.toml
```

### Qwen3 4B Q4, 35 Вт, запуск 1

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch1.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch1.toml
```

### Qwen3 4B Q4, 35 Вт, запуск 2

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch2.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch2.toml
```

### Qwen3 4B Q4, 35 Вт, запуск 3

```powershell
nvidia-smi -pl 35
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch3.toml --json
ollama stop llama3.2:3b-instruct-q4_K_M
ollama stop qwen3:4b-instruct-2507-q4_K_M
.\.venv\Scripts\python.exe -m llm_energy_bench run --config configs/power-quality-v2/rtx5060/qwen3-q4-p35-launch3.toml
```

## Завершение серии RTX 5060

```powershell
nvidia-smi -pl 80
nvidia-smi -q -d POWER
ollama ps
```

Проверьте, что все 24 новых каталога имеют `schema_version = 3`, статус `completed`, пустой список ошибок в `validation.json` и по 60 валидных measured requests. Добавьте каталоги и одну запись в `docs/experiment-log.md`; не запускайте общий анализ до получения полной матрицы трёх стендов.

## RTX 4060 Ti и GTX 1080

Точные блоки этих стендов будут добавлены центрально после получения minimum/default/maximum/current профилей и проверки административной команды `nvidia-smi -pl`. До появления committed TOML коллеги выполняют только профиль из своих заданий. Значения мощности по памяти или из интернета не подставляются.

RTX 4060 Ti получает четыре уровня и роль `primary`; GTX 1080 — три уровня и роль `external`. Порядок команд для каждого будущего TOML полностью совпадает с блоками выше, а завершающая команда возвращает фактический штатный лимит конкретной карты.

## Анализ после трёх серий

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

Анализ обязан отклонить неполную матрицу, schema v2, drift digest/runtime/prompts или смешение ролей.

