# LLM energy benchmark report

Validated runs: 4/4.

Speed and energy rankings differ in at least one aggregate workload block.
This is descriptive only; statistical rank-inversion criteria are evaluated separately.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| pqv2-20261002T020545Z-a07480 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 2 | 64.8331253705 | 0.799466314658 | 0.125 |  |  |
| pqv2-20261002T020545Z-a07480 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 8 | 62.3881778558 | 0.797400489604 | 0.125 |  |  |
| pqv2-20261002T020545Z-a07480 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 2 | 122.028905978 | 1.6813776925 | 0.125 |  |  |
| pqv2-20261002T020702Z-f22870 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 2 | 67.2390141208 | 1.00860977546 | 0.125 |  |  |
| pqv2-20261002T020702Z-f22870 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 8 | 66.7731999493 | 0.889923334522 | 0.125 |  |  |
| pqv2-20261002T020702Z-f22870 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 2 | 124.749198072 | 1.55743973723 | 0.125 |  |  |
| pqv2-20261002T020732Z-fd096b | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 2 | 35.3962555895 | 0.486382469081 | 0.75 | 1 | 2 |
| pqv2-20261002T020732Z-fd096b | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 8 | 26.6064739533 | 0.352712273984 | 0.75 | 2 | 2 |
| pqv2-20261002T020732Z-fd096b | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 2 | 95.2345965714 | 1.21322484462 | 0.75 | 1 | 2 |
| pqv2-20261002T020805Z-efb963 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 2 | 34.9173446251 | 0.512867650394 | 0.75 | 2 | 1 |
| pqv2-20261002T020805Z-efb963 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 8 | 28.8422365703 | 0.387927229415 | 0.75 | 1 | 1 |
| pqv2-20261002T020805Z-efb963 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 2 | 93.9491206426 | 1.21564471401 | 0.75 | 2 | 1 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
