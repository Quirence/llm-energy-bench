# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | long | 40 | 111.953021922 | 1.43345157363 | 0.875 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | scored | 40 | 84.8178211743 | 1.09611442626 | 0.875 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | short | 40 | 122.711920979 | 1.54468923942 | 0.875 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q8_0 | long | 40 | 79.0316950998 | 0.977916725089 | 0.8 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q8_0 | scored | 40 | 56.8582553803 | 0.681425321012 | 0.8 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | llama3.2:3b-instruct-q8_0 | short | 40 | 84.7998124864 | 1.0744714802 | 0.8 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | long | 40 | 83.4376738197 | 1.05664303046 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 36.4251364439 | 0.473467696018 | 1 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | short | 40 | 93.9395640325 | 1.20652744357 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | long | 40 | 61.7784230552 | 0.795093192029 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | scored | 40 | 32.5229558847 | 0.43491383005 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T015412Z-1099aa | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | short | 40 | 67.04265893 | 0.857037171973 | 1 | 4 | 4 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
