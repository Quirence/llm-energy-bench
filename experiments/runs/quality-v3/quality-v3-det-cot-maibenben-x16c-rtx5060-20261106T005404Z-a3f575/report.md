# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| quality-v3-det-cot-maibenben-x16c-rtx5060-20261106T005404Z-a3f575 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 50 | 117.216008954 | 1.49266648142 | 0 |  |  |
| quality-v3-det-cot-maibenben-x16c-rtx5060-20261106T005404Z-a3f575 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q8_0 | scored | 50 | 82.4104441504 | 1.03196464784 | 0 |  |  |
| quality-v3-det-cot-maibenben-x16c-rtx5060-20261106T005404Z-a3f575 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 50 | 91.4202903269 | 1.14729773985 | 0 |  |  |
| quality-v3-det-cot-maibenben-x16c-rtx5060-20261106T005404Z-a3f575 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q8_0 | scored | 50 | 65.8646159065 | 0.833472225761 | 0 |  |  |

GPU energy and cost figures are GPU-only estimates, not wall energy.
