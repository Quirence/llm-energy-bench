# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-rtx4060ti-desktop-20260929T003009Z-f4bcf0 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | long | 6 | 92.1096873446 | 0.821189847844 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T003009Z-f4bcf0 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | scored | 6 | 35.6329979411 | 0.248454334529 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T003009Z-f4bcf0 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | short | 6 | 105.19647209 | 0.953262944337 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
