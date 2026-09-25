# Размер запущенной модели, 2026-09-25

Checkpoint `dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8`, revision `d61c59ea5e514e25d305b5850e8a432f7a9969f2`, 48 safetensors на сервере 8×H100.

Метод: прочитаны JSON-заголовки всех 48 файлов (shape, dtype, data_offsets), без загрузки весов. Элементы I8 в экспертах — упакованный FP4, два параметра на байт (`experts.N.w1.weight` [2304, 2560] при hidden 5120). Масштабы F8_E8M0 в параметры не включались.

| dtype в файлах | элементов, млрд | байт, GB |
|---|---:|---:|
| I8 (упакованный FP4) | 278,59 → 557,17 параметров | 278,59 |
| F8_E4M3 | 204,02 | 204,02 |
| F8_E8M0 (масштабы) | 23,56 | 23,56 |
| BF16 | 1,98 | 3,95 |
| F32 | 0,04 | 0,17 |
| **Итого** | **763,21 параметров** | **510,29** |

Hugging Face API (`/api/models/<repo>?expand[]=safetensors`) у этого репозитория и у базового `deepseek-ai/DeepSeek-V4.1-Flash` даёт одно и то же: BF16 1 976 441 856, F32 42 307 282, F8_E4M3 204 015 223 296, I8 557 171 343 360, итого 763 205 315 794.

По частям модели: routed experts 557,17 (40 слоёв + слой MTP), таблицы Engram (`layers.*.engram.embed.weight`) 196,61 — 202,76 GB = 188,8 GiB, прочее 9,42 (attention 5,13, shared experts 1,52, embed + head 1,32, MTP 0,64, vision 0,41). Без таблиц Engram — 307,53 GB = 286,4 GiB.

Config (`text_config`): 40 слоёв, hidden 5120, `moe_intermediate_size` 2304, 384 routed experts, top-6, 1 shared, словарь 129 280, `max_position_embeddings` 1 048 576.

Активные на токен — расчёт, не замер: 40 × 384 × 3 × 2304 × 5120 × 6/384 = 8,49 млрд в routed experts, плюс shared experts, attention и head, около 7 млрд. Итого около 16 млрд, без строк Engram.
