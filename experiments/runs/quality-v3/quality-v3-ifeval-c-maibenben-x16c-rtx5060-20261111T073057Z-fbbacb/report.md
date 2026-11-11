# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-ifeval-c-maibenben-x16c-rtx5060-20261111T073057Z-fbbacb | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 180 | 119.873323661 | 1.41223767755 |  |  |  |
| quality-v3-ifeval-c-maibenben-x16c-rtx5060-20261111T073057Z-fbbacb | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | long | 180 | 85.3123276669 | 0.943747672467 |  |  |  |
| quality-v3-ifeval-c-maibenben-x16c-rtx5060-20261111T073057Z-fbbacb | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 180 | 93.6769725948 | 1.11466939865 |  |  |  |
| quality-v3-ifeval-c-maibenben-x16c-rtx5060-20261111T073057Z-fbbacb | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | long | 180 | 67.2343061694 | 0.7549669399 |  |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
