# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-direct-p3-maibenben-x16c-rtx5060-20261106T032718Z-048c46 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 57.8672407962 | 0.956537872361 | 0.028 |  |  |
| quality-v3-mgsm-ru-direct-p3-maibenben-x16c-rtx5060-20261106T032718Z-048c46 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 64.7589694236 | 0.921554097193 | 0.008 |  |  |
| quality-v3-mgsm-ru-direct-p3-maibenben-x16c-rtx5060-20261106T032718Z-048c46 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 42.3274197651 | 0.663352262533 | 0.12 |  |  |
| quality-v3-mgsm-ru-direct-p3-maibenben-x16c-rtx5060-20261106T032718Z-048c46 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 36.1842742625 | 0.570720368021 | 0.184 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
