# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-maibenben-x16c-rtx5060-20260929T012225Z-8f048a | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 6 | 101.162538115 | 1.34874933049 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260929T012225Z-8f048a | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 6 | 30.8479484078 | 0.430742803057 | 1 | 1 | 1 |
| pilot-v1-maibenben-x16c-rtx5060-20260929T012225Z-8f048a | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 6 | 121.857911368 | 1.58279660588 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
