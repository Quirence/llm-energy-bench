# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T013223Z-1907d4 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 6 | 76.5476187319 | 0.925624961407 | 1 | 1 | 1 |
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T013223Z-1907d4 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 6 | 31.2809184185 | 0.406244237996 | 1 | 1 | 1 |
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T013223Z-1907d4 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 6 | 94.8099412829 | 1.24669326081 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
