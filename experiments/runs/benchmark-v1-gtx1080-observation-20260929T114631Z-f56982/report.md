# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings differ in at least one aggregate workload block.
This is descriptive only; statistical rank-inversion criteria are evaluated separately.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q4_K_M | long | 40 | 65.9844733283 | 0.363578039138 | 0.825 | 1 | 1 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q4_K_M | scored | 40 | 55.0848591474 | 0.307981951484 | 0.825 | 1 | 1 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q4_K_M | short | 40 | 74.9507558846 | 0.409839131486 | 0.825 | 1 | 1 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q8_0 | long | 40 | 50.8624811383 | 0.307592222527 | 0.75 | 2 | 2 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q8_0 | scored | 40 | 38.5972452964 | 0.237508355976 | 0.75 | 2 | 2 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | llama3.2:3b-instruct-q8_0 | short | 40 | 56.6975650176 | 0.344026633392 | 0.75 | 3 | 2 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q4_K_M | long | 40 | 50.6901571899 | 0.279611701239 | 1 | 3 | 3 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 25.7088078017 | 0.149649140787 | 1 | 3 | 3 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q4_K_M | short | 40 | 60.5634630202 | 0.33057047043 | 1 | 2 | 3 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q8_0 | long | 40 | 40.8877255737 | 0.242445456072 | 1 | 4 | 4 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q8_0 | scored | 40 | 23.2790165216 | 0.14098129819 | 1 | 4 | 4 |
| benchmark-v1-gtx1080-observation-20260929T114631Z-f56982 | gtx1080-observation | qwen3:4b-instruct-2507-q8_0 | short | 40 | 46.1012964172 | 0.27597547268 | 1 | 4 | 4 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
