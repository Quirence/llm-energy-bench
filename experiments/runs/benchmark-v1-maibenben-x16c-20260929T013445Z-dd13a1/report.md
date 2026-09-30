# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | long | 40 | 111.903103712 | 1.42353287953 | 0.825 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | scored | 40 | 83.4021027319 | 1.04120994627 | 0.825 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | short | 40 | 122.71945834 | 1.55294848802 | 0.825 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | long | 40 | 78.905025183 | 0.997827207266 | 0.75 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | scored | 40 | 52.9135994776 | 0.678528956849 | 0.75 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | short | 40 | 84.7411018645 | 1.0650078496 | 0.75 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | long | 40 | 83.2937818254 | 1.0813407667 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 36.5483005279 | 0.485132047152 | 1 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | short | 40 | 93.8341398727 | 1.18539078867 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | long | 40 | 61.7899499618 | 0.7870842354 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | scored | 40 | 32.9673965635 | 0.411785777643 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T013445Z-dd13a1 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | short | 40 | 67.1476856704 | 0.857649307357 | 1 | 4 | 4 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
