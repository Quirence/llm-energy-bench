# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-cot-p2-maibenben-x16c-rtx5060-20261106T022518Z-9837c0 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 118.6475443 | 1.49769918874 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p2-maibenben-x16c-rtx5060-20261106T022518Z-9837c0 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 83.2643780234 | 1.04797172205 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p2-maibenben-x16c-rtx5060-20261106T022518Z-9837c0 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 92.1748203832 | 1.16780778394 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p2-maibenben-x16c-rtx5060-20261106T022518Z-9837c0 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 66.0055145524 | 0.832048305982 | 0 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
