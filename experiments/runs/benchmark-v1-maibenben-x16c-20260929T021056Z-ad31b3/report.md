# LLM energy benchmark report

Validated runs: 1/1.

Speed and energy rankings agree in the observed aggregates.
This does not establish equivalence outside the measured configurations.

| Run | Host | Model | Workload | Requests | tok/s | tok/J | Quality | Speed rank | Energy rank |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | long | 40 | 111.319412754 | 1.42478078529 | 0.85 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | scored | 40 | 82.4627621716 | 1.11803432599 | 0.85 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q4_K_M | short | 40 | 122.582524066 | 1.54902424973 | 0.85 | 1 | 1 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | long | 40 | 78.5644455452 | 1.00441461499 | 0.75 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | scored | 40 | 56.1134996741 | 0.680827589133 | 0.75 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | llama3.2:3b-instruct-q8_0 | short | 40 | 84.6293432003 | 1.07473976579 | 0.75 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | long | 40 | 83.5911642968 | 1.07143536611 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | scored | 40 | 36.2538871579 | 0.457327570283 | 1 | 3 | 3 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q4_K_M | short | 40 | 93.4799043199 | 1.19202981471 | 1 | 2 | 2 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | long | 40 | 61.7487211868 | 0.803204591275 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | scored | 40 | 32.3219311354 | 0.434424748591 | 1 | 4 | 4 |
| benchmark-v1-maibenben-x16c-20260929T021056Z-ad31b3 | maibenben-x16c | qwen3:4b-instruct-2507-q8_0 | short | 40 | 66.8884542799 | 0.85091276248 | 1 | 4 | 4 |

GPU energy and cost figures are GPU-only estimates, not wall energy.
