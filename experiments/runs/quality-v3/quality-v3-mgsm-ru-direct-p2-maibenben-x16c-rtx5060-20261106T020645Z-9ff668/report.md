# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-direct-p2-maibenben-x16c-rtx5060-20261106T020645Z-9ff668 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 54.821692506 | 0.911455768521 | 0.024 |  |  |
| quality-v3-mgsm-ru-direct-p2-maibenben-x16c-rtx5060-20261106T020645Z-9ff668 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 60.9560687758 | 0.869209767221 | 0.004 |  |  |
| quality-v3-mgsm-ru-direct-p2-maibenben-x16c-rtx5060-20261106T020645Z-9ff668 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 42.1556202788 | 0.685149435709 | 0.128 |  |  |
| quality-v3-mgsm-ru-direct-p2-maibenben-x16c-rtx5060-20261106T020645Z-9ff668 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 37.045946353 | 0.56602554976 | 0.172 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
