# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-cot-p3-maibenben-x16c-rtx5060-20261106T033150Z-11324d | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 118.7364482 | 1.50443721889 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p3-maibenben-x16c-rtx5060-20261106T033150Z-11324d | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 83.1269546348 | 1.04452671371 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p3-maibenben-x16c-rtx5060-20261106T033150Z-11324d | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 92.2697585059 | 1.16285175231 | 0 |  |  |
| quality-v3-mgsm-ru-cot-p3-maibenben-x16c-rtx5060-20261106T033150Z-11324d | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 66.1058163148 | 0.835187272941 | 0 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
