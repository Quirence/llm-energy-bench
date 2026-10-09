# Задание Льву: полная серия RTX 4060 Ti для power-quality-v2

Профиль стенда принят. Производственную серию нужно выполнять только по
неизменяемой метке `power-quality-v2-rtx4060ti-code`. Это промежуточная
метка именно для RTX 4060 Ti; общая метка `power-quality-v2-code` будет
выпущена после подготовки GTX 1080.

Зафиксировано заранее:

- стенд `rtx4060ti-desktop`, NVIDIA GeForce RTX 4060 Ti 8188 MiB;
- драйвер `560.94`, схема питания Windows «Сбалансированная»;
- Ollama `0.35.0`;
- модели только `llama3.2:3b-instruct-q4_K_M` и
  `qwen3:4b-instruct-2507-q4_K_M` с уже проверенными digest;
- уровни мощности 100, 130, 160 и 195 Вт;
- 24 запуска: 2 модели × 4 уровня × 3 launch;
- в каждом запуске 12 запросов × 5 повторений = 60 измерений;
- итог серии — 1440 измеряемых запросов плюс исключённые прогревы.

Код, prompts и TOML менять нельзя. Модели повторно загружать или обновлять
нельзя.

## 1. Подготовка чистой копии

Открой обычную PowerShell, клонируй репозиторий в новый каталог и перейди в
него. Если чистый клон уже есть, первая команда не нужна.

```powershell
git clone https://github.com/Quirence/llm-energy-bench.git
cd llm-energy-bench
git fetch --tags origin
git checkout power-quality-v2-rtx4060ti-code
git switch -c data/rtx4060ti-power-quality-v2
git status --short
```

Последняя команда обязана вывести пустую строку. Затем создай окружение из
зафиксированного проекта и проверь код:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Любой ненулевой exit code — остановка и сообщение Quirence. Не исправляй
тесты или зависимости на своей ветке.

## 2. Обновление Ollama ровно до 0.35.0

В профиле была версия 0.34.2, поэтому до серии её обязательно заменить на
0.35.0. Используй официальный установщик именно релиза
[v0.35.0](https://github.com/ollama/ollama/releases/tag/v0.35.0), а не
автообновление до более новой версии.

```powershell
$installer = Join-Path $env:TEMP "OllamaSetup-0.35.0.exe"
Invoke-WebRequest `
  -Uri "https://github.com/ollama/ollama/releases/download/v0.35.0/OllamaSetup.exe" `
  -OutFile $installer
(Get-FileHash $installer -Algorithm SHA256).Hash
```

Ожидаемый SHA-256 официального файла:
`92E45C3518DAF7D4EA60480896EE7BDB1BED71381593CFC9F2D7C1CEB941EFDE`.
Если хеш отличается, файл не запускай. При совпадении:

```powershell
Start-Process -FilePath $installer -Wait
ollama --version
ollama list
```

Версия должна быть ровно `0.35.0`, а ID двух Q4-моделей должны начинаться с
`a80c4f17acd5` и `0edcdef34593`. Не выполняй `ollama pull`: производственный
скрипт сам проверит полные digest.

## 3. Подготовка ПК

Перед началом:

1. Перезагрузи ПК после установки Ollama, если установщик это потребует.
2. Оставь схему питания Windows «Сбалансированная» и питание от сети.
3. Закрой Wallpaper Engine, Firefox/Chrome, Discord, Steam overlay,
   видеоплееры, Zed, Claude и другие программы с аппаратным ускорением.
4. Не обновляй драйвер `560.94` до завершения серии.
5. Не запускай игры, видео, удалённый рабочий стол и параллельные задачи GPU.

Скрипт допускает перед загрузкой модели не более 5% GPU, 50 °C и 2048 MiB
VRAM; runner дополнительно измеряет 15-секундный фон и требует p95 загрузки
не более 5%, температуру не выше 55 °C и точное совпадение power limit.

## 4. Проверка плана без изменений

Открой **PowerShell от имени администратора** в каталоге репозитория и
сначала выведи расписание:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-rtx4060ti.ps1
```

Должно быть ровно 24 строки. На этом шаге power limit и результаты не
изменяются.

## 5. Полная серия

Не меняя окно и окружение, запусти:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-rtx4060ti.ps1 -Execute
```

Скрипт сам:

- требует точную Git-метку, чистую ветку, Ollama 0.35.0, драйвер 560.94 и
  профиль RTX 4060 Ti 100–195 Вт;
- задаёт power limit через `nvidia-smi -pl`;
- чередует уровни и порядок моделей по заранее зафиксированному расписанию;
- перед каждым запуском выгружает обе модели и ждёт охлаждения GPU;
- выполняет `doctor`, снова выгружает модели и запускает `run`;
- немедленно останавливается при любой ошибке;
- в блоке `finally` возвращает штатные 160 Вт;
- после серии принимает только 24 schema-v3 run с 1440/1440 валидными
  запросами и создаёт `rtx4060ti-campaign-receipt.json`.

Не запускай скрипт повторно после ошибки и не удаляй failed run. Скопируй
последние строки консоли и сообщи Quirence: повторный запуск согласуем по
сохранённым артефактам.

## 6. Загрузка результатов

Только если скрипт напечатал `Series accepted locally: 24/24 runs` и
подтвердил возврат 160 Вт:

```powershell
git status --short
git add experiments/runs/power-quality-v2
git diff --cached --stat
git commit -m "data: add RTX 4060 Ti power quality v2 campaign"
git push -u origin data/rtx4060ti-power-quality-v2
```

В коммит должны попасть только 24 новых run-каталога и один receipt. Не
добавляй `.venv`, сырые профили, код, configs, prompts или исправленные
результаты. После push пришли Quirence имя ветки и ссылку, которую GitHub
покажет для создания Pull Request. Центральный исполнитель отдельно проверит
артефакты, добавит запись в `docs/experiment-log.md` и только затем объединит
данные.
