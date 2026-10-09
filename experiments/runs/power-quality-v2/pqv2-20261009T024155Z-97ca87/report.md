# LLM energy benchmark report

Validated runs: 12/12.

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
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 32.2846971596 | 0.475338367495 | 0.75 | 6 | 1 |
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 27.0457482889 | 0.413219751069 | 0.75 | 6 | 1 |
| pqv2-20261009T024547Z-d0889e | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 91.3311670651 | 1.13056781044 | 0.75 | 6 | 2 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 33.6483111684 | 0.440287421138 | 0.75 | 4 | 3 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 28.6796265597 | 0.388178220559 | 0.75 | 4 | 2 |
| pqv2-20261009T024659Z-479549 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 92.1894129585 | 1.12780036876 | 0.75 | 5 | 3 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 33.4059977415 | 0.456787261125 | 0.75 | 5 | 2 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 28.2599401101 | 0.35970505121 | 0.75 | 5 | 3 |
| pqv2-20261009T024841Z-19c9e5 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 92.6290284193 | 1.15410269765 | 0.75 | 4 | 1 |
| pqv2-20261009T025429Z-50b8bb | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 68.8326854376 | 0.690119299079 | 0.075 |  |  |
| pqv2-20261009T025429Z-50b8bb | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 70.6296621846 | 0.774547506396 | 0.075 |  |  |
| pqv2-20261009T025429Z-50b8bb | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 127.015759642 | 1.23250238714 | 0.075 |  |  |
| pqv2-20261009T025532Z-a642d0 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 69.6050931089 | 0.820140737313 | 0.075 |  |  |
| pqv2-20261009T025532Z-a642d0 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 72.8977507248 | 0.75757015085 | 0.075 |  |  |
| pqv2-20261009T025532Z-a642d0 | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 127.336810914 | 1.17944998133 | 0.075 |  |  |
| pqv2-20261009T025656Z-996c1f | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | long | 10 | 71.6489343773 | 0.790496811196 | 0.075 |  |  |
| pqv2-20261009T025656Z-996c1f | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | scored | 40 | 75.8615351022 | 0.797085927426 | 0.075 |  |  |
| pqv2-20261009T025656Z-996c1f | maibenben-x16c-rtx5060 | llama3.2:3b-instruct-q4_K_M | short | 10 | 127.438701743 | 1.21630745444 | 0.075 |  |  |
| pqv2-20261009T025808Z-2f25db | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 34.8036309534 | 0.367750565929 | 0.75 | 3 | 6 |
| pqv2-20261009T025808Z-2f25db | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 28.6988645127 | 0.28221978822 | 0.75 | 3 | 6 |
| pqv2-20261009T025808Z-2f25db | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 97.7089048064 | 0.934968063513 | 0.75 | 1 | 5 |
| pqv2-20261009T025946Z-5f5f60 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 36.4763264212 | 0.405758106919 | 0.75 | 1 | 5 |
| pqv2-20261009T025946Z-5f5f60 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 30.3592900541 | 0.33112925789 | 0.75 | 2 | 4 |
| pqv2-20261009T025946Z-5f5f60 | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 97.4212088468 | 0.929510799759 | 0.75 | 2 | 6 |
| pqv2-20261009T030124Z-6224ab | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | long | 10 | 35.7149672142 | 0.420714092123 | 0.75 | 2 | 4 |
| pqv2-20261009T030124Z-6224ab | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 30.6492116001 | 0.312217088226 | 0.75 | 1 | 5 |
| pqv2-20261009T030124Z-6224ab | maibenben-x16c-rtx5060 | qwen3:4b-instruct-2507-q4_K_M | short | 10 | 96.1208547933 | 0.939432478777 | 0.75 | 3 | 4 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
