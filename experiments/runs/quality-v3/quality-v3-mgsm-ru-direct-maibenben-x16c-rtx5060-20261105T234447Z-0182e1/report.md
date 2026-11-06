# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-mgsm-ru-direct-maibenben-x16c-rtx5060-20261105T234447Z-0182e1 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 250 | 48.4385692374 | 0.743198307852 | 0.016 |  |  |
| quality-v3-mgsm-ru-direct-maibenben-x16c-rtx5060-20261105T234447Z-0182e1 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 250 | 59.1302571196 | 0.77836582663 | 0.008 |  |  |
| quality-v3-mgsm-ru-direct-maibenben-x16c-rtx5060-20261105T234447Z-0182e1 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 250 | 39.8106641688 | 0.631110155126 | 0.124 |  |  |
| quality-v3-mgsm-ru-direct-maibenben-x16c-rtx5060-20261105T234447Z-0182e1 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 250 | 35.4275826548 | 0.536900692035 | 0.18 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
