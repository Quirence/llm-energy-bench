# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 102.847691626 | 1.29675941833 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 31.577044435 | 0.427772883534 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 121.95207725 | 1.46321491263 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
