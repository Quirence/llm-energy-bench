# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-det-direct-maibenben-x16c-rtx5060-20261106T005146Z-13a588 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 50 | 65.3503757341 | 0.994161711945 | 0.04 |  |  |
| quality-v3-det-direct-maibenben-x16c-rtx5060-20261106T005146Z-13a588 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 50 | 70.4821117407 | 0.947107806233 | 0.02 |  |  |
| quality-v3-det-direct-maibenben-x16c-rtx5060-20261106T005146Z-13a588 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 50 | 30.6956343813 | 0.473034967665 | 0.14 |  |  |
| quality-v3-det-direct-maibenben-x16c-rtx5060-20261106T005146Z-13a588 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 50 | 42.9214521187 | 0.611380757626 | 0.18 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
