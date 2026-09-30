# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pilot-v1-rtx4060ti-desktop-20260929T003046Z-9daa3d | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | long | 6 | 92.2759150437 | 0.869874377816 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T003046Z-9daa3d | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | scored | 6 | 36.7524212849 | 0.352762128946 | 1 | 1 | 1 |
| pilot-v1-rtx4060ti-desktop-20260929T003046Z-9daa3d | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | short | 6 | 104.961818415 | 0.952480272535 | 1 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
