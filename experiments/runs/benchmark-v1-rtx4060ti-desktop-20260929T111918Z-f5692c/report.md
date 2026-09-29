# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | long | 40 | 96.0284549812 | 0.866459674625 | 0.85 | 1 | 1 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | scored | 40 | 84.3838495264 | 0.731399119985 | 0.85 | 1 | 1 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q4_K_M | short | 40 | 102.444379518 | 0.9188439182 | 0.85 | 1 | 1 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q8_0 | long | 40 | 62.4585129191 | 0.657983043419 | 0.725 |  |  |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q8_0 | scored | 40 | 50.7315144333 | 0.506358964115 | 0.725 |  |  |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | llama3.2:3b-instruct-q8_0 | short | 40 | 64.4960650763 | 0.687062345044 | 0.725 |  |  |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q4_K_M | long | 40 | 76.7087103318 | 0.686901932732 | 1 | 2 | 2 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 43.9749647594 | 0.428067785696 | 1 | 2 | 2 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q4_K_M | short | 40 | 82.6283444091 | 0.734008414266 | 1 | 2 | 2 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q8_0 | long | 40 | 49.7298737323 | 0.515673582148 | 1 | 3 | 3 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q8_0 | scored | 40 | 33.7279310482 | 0.383954510745 | 1 | 3 | 3 |
| benchmark-v1-rtx4060ti-desktop-20260929T111918Z-f5692c | rtx4060ti-desktop | qwen3:4b-instruct-2507-q8_0 | short | 40 | 52.3363995785 | 0.542625932479 | 1 | 3 | 3 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
