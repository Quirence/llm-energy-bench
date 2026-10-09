# Задание Диме: профиль GTX 1080 и внешняя серия power-quality-v2

## Сейчас: только аппаратный профиль

1. Не меняй код, prompts и TOML.
2. Открой PowerShell от имени администратора в чистом клоне репозитория.
3. Выполни команды и пришли Quirence весь вывод личным сообщением. Не коммить
   сырой вывод `nvidia-smi -q`: сначала он будет санитизирован.

```powershell
git fetch --tags origin
git checkout power-quality-v2-profile
git status --short
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/profile-gtx1080.toml --json
nvidia-smi -q -d POWER,TEMPERATURE,MEMORY
ollama ps
ollama --version
ollama list
```

Если метка `power-quality-v2-profile` ещё не опубликована, остановись. Эта
метка предназначена только для профилирования; производственные измерения по
ней запускать нельзя. Если локальной `.venv` нет, создай её по README проекта
без произвольного обновления зависимостей.

В сообщении отдельно укажи:

- current, requested, default, minimum и maximum power limit;
- драйвер, точное имя GPU и объём VRAM;
- проходит ли `nvidia-smi -pl <значение>` из административной PowerShell;
- версию Ollama и ID обеих Q4-моделей;
- температуру, VRAM и фоновые GPU-программы во время профиля.

GTX 1080 имеет роль `external`: её результаты не входят в объединённый вывод
двух основных GPU. После профиля Quirence/Codex добавит 18 конфигураций: две
Q4-модели × три проверенных уровня × три запуска. Нужны обе модели из задания;
если одна не помещается полностью в VRAM, сообщи это и не начинай серию.

## После второго сообщения от Quirence

Начинай измерения только после публикации финальной метки
`power-quality-v2-code`, появления каталога
`configs/power-quality-v2/gtx1080/` и прямого подтверждения. Выполняй
`docs/power-quality-v2-runbook.md`. При ненулевом exit code остановись, ничего
не исправляй в артефактах. После серии верни штатный power limit, добавь только
новые каталоги `experiments/runs/power-quality-v2/` и одну запись в
`docs/experiment-log.md`, затем открой PR. Код, prompts, config и анализ не
менять.
