# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-ifeval-a-maibenben-x16c-rtx5060-20261107T074009Z-5b0b9d | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 180 | 122.850631504 | 1.38114709721 |  |  |  |
| quality-v3-ifeval-a-maibenben-x16c-rtx5060-20261107T074009Z-5b0b9d | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | long | 180 | 83.7435137675 | 0.91918982376 |  |  |  |
| quality-v3-ifeval-a-maibenben-x16c-rtx5060-20261107T074009Z-5b0b9d | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 180 | 91.7785626569 | 1.10771333837 |  |  |  |
| quality-v3-ifeval-a-maibenben-x16c-rtx5060-20261107T074009Z-5b0b9d | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | long | 180 | 66.6456034975 | 0.743463645954 |  |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
