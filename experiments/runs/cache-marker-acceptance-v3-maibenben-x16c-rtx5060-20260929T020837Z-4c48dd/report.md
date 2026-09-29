# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T020837Z-4c48dd | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 6 | 75.9651830279 | 0.888946420128 | 1 | 1 | 1 |
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T020837Z-4c48dd | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 6 | 34.479122461 | 0.379052458722 | 1 | 1 | 1 |
| cache-marker-acceptance-v3-maibenben-x16c-rtx5060-20260929T020837Z-4c48dd | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 6 | 94.7262705721 | 1.15019171204 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
