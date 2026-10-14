# Задание Диме: внешняя серия GTX 1080 для power-quality-v2

> Статус: выполнено по метке `power-quality-v2-gtx1080-code-v3`.
> Приняты 18/18 запусков и 1080/1080 валидных запросов. Повторять серию не
> требуется; команды ниже сохранены для аудита процедуры.

Производственная серия выполнена по неизменяемой метке
`power-quality-v2-gtx1080-code-v3`. Предыдущие метки отозваны до начала
принятой серии: аппаратный preflight Димы подтвердил minimum 90 Вт вместо
предварительно принятого minimum 100 Вт, а v3 исправила обработку вывода
`ollama stop`. GTX 1080 имеет роль
`external`: её данные показываются отдельным блоком и не входят в объединённый
вывод двух основных GPU.

Зафиксировано до измерений:

- стенд `gtx1080-observation`, Palit GeForce GTX 1080 GameRock, 8192 MiB;
- драйвер `582.66`;
- подтверждённый профиль BIOS: default 200 Вт, minimum 90 Вт, maximum 240 Вт;
- исследуемые уровни 100, 150 и 200 Вт; 240 Вт намеренно не используется,
  потому что эксперимент проверяет снижение относительно штатных 200 Вт, а не
  разгон старой карты;
- Ollama `0.35.0`;
- модели только `llama3.2:3b-instruct-q4_K_M` и
  `qwen3:4b-instruct-2507-q4_K_M` с уже проверенными digest;
- 18 запусков: 2 модели × 3 уровня × 3 launch;
- в каждом запуске 12 запросов × 5 повторений = 60 измерений;
- итог серии — 1080 измеряемых запросов плюс исключённые прогревы.

Профиль мощности основан на сохранённом наблюдении этого стенда и фактическом
аппаратном preflight Димы: карта сообщила default/minimum/maximum
`200/90/240 Вт`. Скрипт до первого изменения мощности повторно считывает эти
значения. Если BIOS карты сообщает другие значения, серия остановится до
измерений. В таком случае ничего не исправляй вручную: пришли Quirence строку
ошибки, после чего центрально будет выпущена исправленная метка.

Код, prompts и TOML менять нельзя. Модели повторно загружать или обновлять
нельзя.

## 1. Подготовка чистой копии

Открой обычную PowerShell, клонируй репозиторий в новый каталог и перейди в
него. Если чистый клон уже есть, первая команда не нужна.

```powershell
git clone https://github.com/Quirence/llm-energy-bench.git
cd llm-energy-bench
git fetch --tags origin
git checkout power-quality-v2-gtx1080-code-v3
git switch -c data/gtx1080-power-quality-v2
git status --short
```

Последняя команда обязана вывести пустую строку. Затем создай окружение из
зафиксированного проекта и проверь код:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/power-quality-v2-windows-py312.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Lock предназначен для CPython 3.12 x86-64 на Windows, содержит точные версии
и SHA-256 всех runtime/dev/build wheels. Его SHA-256 равен
`474a00ce6ca43b0ee2a411dcd71f79a95ef7a94d7ffe699cfb1becc80c4662c0`.
Скрипт ещё раз сравнит lock, Python и установленные версии перед первым
изменением мощности, а затем запишет их в receipt.

Любой ненулевой exit code — остановка и сообщение Quirence. Не исправляй
тесты или зависимости на своей ветке.

## 2. Обновление Ollama ровно до 0.35.0

Исторические прогоны выполнялись на 0.34.2, поэтому до серии её нужно заменить
на 0.35.0. Используй официальный установщик именно релиза
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
`a80c4f17acd5` и `0edcdef34593`. Не выполняй `ollama pull`:
производственный скрипт сам проверит полные digest.

## 3. Подготовка ПК

Перед началом:

1. Перезагрузи ПК после установки Ollama, если установщик это потребует.
2. Оставь обычную схему питания Windows и питание от сети.
3. Закрой Wallpaper Engine, браузеры, Discord, Steam overlay, видеоплееры,
   редакторы и другие программы с аппаратным ускорением.
4. Не обновляй драйвер `582.66` до завершения серии.
5. Не меняй BIOS, положение его переключателя, разгон, undervolt, кривую
   напряжения или настройки MSI Afterburner/ThunderMaster.
6. Не запускай игры, видео, удалённый рабочий стол и параллельные задачи GPU.

Скрипт допускает перед загрузкой модели не более 5% GPU, 50 °C и 2048 MiB
VRAM; runner дополнительно измеряет 15-секундный фон и требует p95 загрузки
не более 5%, температуру не выше 55 °C и точное совпадение power limit.

## 4. Проверка плана без изменений

Открой **PowerShell от имени администратора** в каталоге репозитория и сначала
выведи расписание:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-gtx1080.ps1
```

Должно быть ровно 18 строк. На этом шаге power limit и результаты не
изменяются.

## 5. Полная серия

Не меняя окно и окружение, запусти:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-power-quality-v2-gtx1080.ps1 -Execute
```

Скрипт сам:

- требует точную Git-метку, чистую ветку, Ollama 0.35.0, драйвер 582.66 и
  профиль GTX 1080 default/min/max 200/90/240 Вт;
- проверяет SHA-256 dependency lock и версии Python-пакетов;
- задаёт 100, 150 и 200 Вт через `nvidia-smi -pl`;
- чередует уровни и порядок моделей по заранее зафиксированному расписанию;
- перед каждым запуском выгружает обе модели и ждёт охлаждения GPU;
- выполняет `doctor`, снова выгружает модели и запускает `run`;
- немедленно останавливается при любой ошибке;
- в блоке `finally` возвращает штатные 200 Вт и повторно читает фактический
  лимит; ошибка серии и ошибка восстановления выводятся вместе;
- после серии принимает только 18 schema-v3 run с 1080/1080 валидными
  запросами, точной матрицей model/power/launch/condition и создаёт
  `gtx1080-campaign-receipt.json`.

Не запускай скрипт повторно после ошибки и не удаляй failed run. Скопируй
последние строки консоли и сообщи Quirence: повторный запуск согласуем по
сохранённым артефактам.

## 6. Загрузка результатов

Только если скрипт напечатал `Series accepted locally: 18/18 runs` и
подтвердил возврат 200 Вт:

```powershell
git status --short
git add experiments/runs/power-quality-v2
git diff --cached --stat
git commit -m "data: add GTX 1080 power quality v2 campaign"
git push -u origin data/gtx1080-power-quality-v2-v2
```

В коммит должны попасть только 18 новых run-каталогов и один receipt. Не
добавляй `.venv`, сырые профили, код, configs, prompts или исправленные
результаты. После push пришли Quirence имя ветки и ссылку, которую GitHub
покажет для создания Pull Request. Центральный исполнитель отдельно проверит
артефакты и только затем объединит данные.
