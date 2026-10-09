# LLM energy benchmark report

Validated runs: 6/6.

Speed and energy rankings differ in at least one aggregate workload block.
This is descriptive only; statistical rank-inversion criteria are evaluated separately.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pqv2-20261009T024155Z-97ca87 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 63.910034543 | 0.847944396544 | 0.075 |  |  |
| pqv2-20261009T024155Z-97ca87 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 68.0467966276 | 0.978983768766 | 0.075 |  |  |
| pqv2-20261009T024155Z-97ca87 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 117.642132207 | 1.41077935304 | 0.075 |  |  |
| pqv2-20261009T024331Z-304149 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 65.6631773555 | 0.846073533724 | 0.075 |  |  |
| pqv2-20261009T024331Z-304149 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 69.7482200688 | 1.04053897998 | 0.075 |  |  |
| pqv2-20261009T024331Z-304149 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 119.421841874 | 1.4863327611 | 0.075 |  |  |
| pqv2-20261009T024434Z-f3fb61 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 66.3027584739 | 0.792267810025 | 0.075 |  |  |
| pqv2-20261009T024434Z-f3fb61 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 71.0960995039 | 1.00046321151 | 0.075 |  |  |
| pqv2-20261009T024434Z-f3fb61 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 119.431227126 | 1.37677283907 | 0.075 |  |  |
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 32.2846971596 | 0.475338367495 | 0.75 | 3 | 1 |
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 27.0457482889 | 0.413219751069 | 0.75 | 3 | 1 |
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 91.3311670651 | 1.13056781044 | 0.75 | 3 | 2 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 33.6483111684 | 0.440287421138 | 0.75 | 1 | 3 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 28.6796265597 | 0.388178220559 | 0.75 | 1 | 2 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 92.1894129585 | 1.12780036876 | 0.75 | 2 | 3 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 33.4059977415 | 0.456787261125 | 0.75 | 2 | 2 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 28.2599401101 | 0.35970505121 | 0.75 | 2 | 3 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 92.6290284193 | 1.15410269765 | 0.75 | 1 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
