# Методические и технические источники

Эти карточки поддерживают методику и ограничения статьи. Они не заменяют
ближайшие эмпирические аналоги из `international/`.

| Код | Источник | Роль в статье |
| --- | --- | --- |
| [R04](R04-nvml.md) | NVIDIA NVML | доступные показатели GPU |
| [R05](R05-ollama-metrics.md) | Ollama API | длительности и счётчики токенов |
| [R06](R06-rigorous-benchmarking.md) | Kalibera, Jones, 2013 | повторения и неопределённость |
| [R07](R07-reproducibility.md) | Pineau et al., 2021 | воспроизводимость |
| [R08](R08-energy-reporting.md) | Henderson et al., 2020 | границы измерения энергии |
| [R09](R09-gptq.md) | Frantar et al., 2023 | квантование после обучения |
| [R10](R10-awq.md) | Lin et al., 2024 | квантование с учётом активаций |
| [R11](R11-zeus.md) | You et al., 2023 | различие оптимума скорости и энергии |
| [R13](R13-mlperf-power.md) | MLCommons | правила измерения мощности |
| [R14](R14-bootstrap.md) | Efron, Tibshirani, 1986 | доверительные интервалы |
| [R15](R15-steady-state.md) | Georges et al., 2007 | прогрев и установившийся режим |
| [R16](R16-benchmark-aggregation.md) | Fleming, Wallace, 1986 | агрегирование отношений |
| [R17](R17-paged-attention.md) | Kwon et al., 2023 | отличие серверного режима |
| [R18](R18-llm-int8.md) | Dettmers et al., 2022 | восьмибитные вычисления |
| [R19](R19-qwen3-report.md) | Qwen Team, 2025 | описание Qwen3 |
| [R20](R20-llama32-model-card.md) | Meta, 2024 | описание Llama 3.2 |
| [M01](M01-llamacpp-quantization.md) | llama.cpp | форматы квантования GGUF |
| [M02](M02-ollama-openapi.md) | Ollama | контракт программного интерфейса |
| [M03](M03-mlcommons-guide.md) | MLCommons | внешнее измерение мощности |

R04, R05, R13, R20 и M01–M03 являются техническими первоисточниками, а не
научными статьями. Их следует цитировать только для описания интерфейсов,
правил измерения, форматов и моделей.
