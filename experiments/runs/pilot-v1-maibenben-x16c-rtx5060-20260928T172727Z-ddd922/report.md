# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 102.114201606 | 1.25945731816 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 33.3661619297 | 0.448883889471 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 122.284507888 | 1.55223601444 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
