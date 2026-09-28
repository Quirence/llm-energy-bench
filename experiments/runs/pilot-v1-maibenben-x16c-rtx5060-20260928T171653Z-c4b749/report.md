# LLM energy benchmark report

Validated runs: 3/3.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 99.7963100729 | 1.22149752981 | 1 | 3 | 3 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 28.6002535419 | 0.39789517432 | 1 | 3 | 3 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 121.437224491 | 1.41306983123 | 1 | 3 | 3 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 102.114201606 | 1.25945731816 | 1 | 2 | 2 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 33.3661619297 | 0.448883889471 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172727Z-ddd922 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 122.284507888 | 1.55223601444 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 102.847691626 | 1.29675941833 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 31.577044435 | 0.427772883534 | 1 | 2 | 2 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T172842Z-eeabf6 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 121.95207725 | 1.46321491263 | 1 | 2 | 2 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
