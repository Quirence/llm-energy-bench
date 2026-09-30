# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-rtx4060ti-desktop-20260929T002903Z-552fa9 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | long | 6 | 92.6782184864 | 0.890954108478 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T002903Z-552fa9 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | scored | 6 | 39.9270931398 | 0.378077527448 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T002903Z-552fa9 | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | short | 6 | 105.776503303 | 0.938815985922 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
