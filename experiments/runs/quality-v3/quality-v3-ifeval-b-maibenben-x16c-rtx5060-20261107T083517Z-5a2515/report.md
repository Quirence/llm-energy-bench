# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-ifeval-b-maibenben-x16c-rtx5060-20261107T083517Z-5a2515 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 180 | 117.307213147 | 1.48556251058 |  |  |  |
| quality-v3-ifeval-b-maibenben-x16c-rtx5060-20261107T083517Z-5a2515 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | long | 180 | 83.354411288 | 1.0507897618 |  |  |  |
| quality-v3-ifeval-b-maibenben-x16c-rtx5060-20261107T083517Z-5a2515 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 180 | 90.3187983052 | 1.14582777708 |  |  |  |
| quality-v3-ifeval-b-maibenben-x16c-rtx5060-20261107T083517Z-5a2515 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | long | 180 | 65.2940773975 | 0.819847619474 |  |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
