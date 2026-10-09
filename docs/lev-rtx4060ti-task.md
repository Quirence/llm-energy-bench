# Задание Льву: профиль RTX 4060 Ti и серия power-quality-v2

## Сейчас: только аппаратный профиль

1. Не меняй код, prompts и TOML.
2. Открой PowerShell от имени администратора в чистом клоне репозитория.
3. Выполни команды и пришли Quirence весь вывод личным сообщением. Не коммить
   сырой вывод `nvidia-smi -q`: сначала он будет санитизирован.

```powershell
git fetch --tags origin
git checkout power-quality-v2-profile
git status --short
.\.venv\Scripts\python.exe -m llm_energy_bench doctor --config configs/power-quality-v2/profile-rtx4060ti.toml --json
nvidia-smi -q -d POWER,TEMPERATURE,MEMORY
ollama ps
ollama --version
ollama list
```

Если метка `power-quality-v2-profile` ещё не опубликована, остановись. Эта
метка предназначена только для профилирования; производственные измерения по
ней запускать нельзя. Если локальной `.venv` нет, создай её по README проекта,
но не обновляй зависимости сверх lock/pyproject.

В сообщении отдельно укажи:

- current, requested, default, minimum и maximum power limit;
- драйвер, точное имя GPU и объём VRAM;
- проходит ли `nvidia-smi -pl <значение>` из административной PowerShell;
- версию Ollama и четыре строки `ollama list` с ID моделей;
- температуру, VRAM и фоновые GPU-программы во время профиля.

После получения профиля Quirence/Codex добавит 24 конфигурации: две Q4-модели
× четыре проверенных уровня × три запуска. Runtime всех участников будет
Ollama 0.35.0; при другой версии не обновляйся самовольно, а сначала сообщи её.

## После второго сообщения от Quirence

Начинай измерения только после публикации финальной метки
`power-quality-v2-code`, появления каталога
`configs/power-quality-v2/rtx4060ti/` и прямого подтверждения. Выполняй
`docs/power-quality-v2-runbook.md` без изменения порядка команд. На каждом
условии сначала устанавливается указанный лимит, затем запускается `doctor`,
обе модели снова выгружаются, и только потом запускается `run`.

При любом ненулевом exit code серию остановить. Результаты не исправлять
вручную. После всех валидных запусков вернуть штатный power limit, добавить
только новые каталоги `experiments/runs/power-quality-v2/` и одну запись в
`docs/experiment-log.md`, затем открыть PR. Код, prompts, config и анализ в
этом PR не менять.
