# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 99.7963100729 | 1.22149752981 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 28.6002535419 | 0.39789517432 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260928T171653Z-c4b749 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 121.437224491 | 1.41306983123 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
