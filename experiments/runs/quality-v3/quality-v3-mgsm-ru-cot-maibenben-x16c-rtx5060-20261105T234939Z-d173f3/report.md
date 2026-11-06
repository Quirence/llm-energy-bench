# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-cot-maibenben-x16c-rtx5060-20261105T234939Z-d173f3 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 117.031090089 | 1.39042417908 | 0 |  |  |
| quality-v3-mgsm-ru-cot-maibenben-x16c-rtx5060-20261105T234939Z-d173f3 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 82.4102141532 | 0.91424741052 | 0 |  |  |
| quality-v3-mgsm-ru-cot-maibenben-x16c-rtx5060-20261105T234939Z-d173f3 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 91.2697143684 | 1.03646361223 | 0 |  |  |
| quality-v3-mgsm-ru-cot-maibenben-x16c-rtx5060-20261105T234939Z-d173f3 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 65.5842771648 | 0.752848414549 | 0 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
