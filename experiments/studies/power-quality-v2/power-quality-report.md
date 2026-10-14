# Анализ power-quality-v2

Основных сравнительных строк: 36.
Внешних наблюдательных строк: 18.
Конфигураций на границе компромисса: 33.

GTX 1080 имеет роль external и не объединяется с основными GPU.
Относительные изменения рассчитаны от максимального лимита мощности для той же модели и нагрузки.

| Стенд | Роль | Модель | Вт | Нагрузка | ток/с | ток/Дж | Точность | Граница |
|---|---|---|---:|---|---:|---:|---:|---|
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 200 | long | 75.773 | 0.162 | — | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 200 | scored | 87.371 | 0.272 | 0.075 | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 200 | short | 77.162 | 0.408 | — | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 150 | long | 73.512 | 0.199 | — | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 150 | scored | 84.984 | 0.331 | 0.075 | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 150 | short | 75.027 | 0.491 | — | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 100 | long | 66.351 | 0.252 | — | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 100 | scored | 78.585 | 0.436 | 0.075 | да |
| gtx1080-observation | external | llama3.2:3b-instruct-q4_K_M | 100 | short | 68.811 | 0.669 | — | да |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 200 | long | 64.709 | 0.076 | — | нет |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 200 | scored | 91.656 | 0.119 | 0.750 | да |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 200 | short | 62.708 | 0.329 | — | нет |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 150 | long | 62.589 | 0.093 | — | нет |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 150 | scored | 87.018 | 0.148 | 0.750 | да |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 150 | short | 61.143 | 0.397 | — | нет |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 100 | long | 57.033 | 0.117 | — | нет |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 100 | scored | 81.334 | 0.182 | 0.750 | да |
| gtx1080-observation | external | qwen3:4b-instruct-2507-q4_K_M | 100 | short | 55.675 | 0.539 | — | нет |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 115 | long | 128.040 | 0.763 | — | да |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 115 | scored | 133.451 | 0.776 | 0.075 | да |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 115 | short | 132.005 | 1.209 | — | да |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 80 | long | 121.210 | 0.828 | — | да |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 80 | scored | 126.929 | 1.006 | 0.075 | да |
| maibenben-x16c-rtx5060 | primary | llama3.2:3b-instruct-q4_K_M | 80 | short | 123.409 | 1.423 | — | да |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 115 | long | 93.114 | 0.397 | — | нет |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 115 | scored | 110.916 | 0.307 | 0.750 | да |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 115 | short | 100.451 | 0.935 | — | нет |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 80 | long | 87.125 | 0.457 | — | нет |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 80 | scored | 105.520 | 0.386 | 0.750 | да |
| maibenben-x16c-rtx5060 | primary | qwen3:4b-instruct-2507-q4_K_M | 80 | short | 95.265 | 1.137 | — | нет |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 195 | long | 114.792 | 0.621 | — | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 195 | scored | 127.306 | 0.729 | 0.075 | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 195 | short | 114.769 | 0.957 | — | нет |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 160 | long | 114.853 | 0.613 | — | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 160 | scored | 127.291 | 0.726 | 0.075 | нет |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 160 | short | 114.701 | 0.960 | — | нет |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 130 | long | 114.621 | 0.664 | — | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 130 | scored | 127.272 | 0.759 | 0.075 | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 130 | short | 115.011 | 0.979 | — | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 100 | long | 113.566 | 0.793 | — | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 100 | scored | 126.668 | 0.900 | 0.075 | да |
| rtx4060ti-desktop | primary | llama3.2:3b-instruct-q4_K_M | 100 | short | 113.872 | 1.264 | — | да |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 195 | long | 93.700 | 0.331 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 195 | scored | 127.434 | 0.361 | 0.750 | да |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 195 | short | 91.712 | 0.759 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 160 | long | 93.729 | 0.364 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 160 | scored | 127.522 | 0.356 | 0.750 | да |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 160 | short | 91.760 | 0.759 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 130 | long | 93.742 | 0.388 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 130 | scored | 127.136 | 0.379 | 0.750 | да |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 130 | short | 91.761 | 0.789 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 100 | long | 92.339 | 0.444 | — | нет |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 100 | scored | 125.843 | 0.445 | 0.750 | да |
| rtx4060ti-desktop | primary | qwen3:4b-instruct-2507-q4_K_M | 100 | short | 90.257 | 0.994 | — | нет |
