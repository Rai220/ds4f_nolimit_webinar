# Квантизованные варианты: ссылки и первый стенд

Проверено 2026-09-22 по карточкам, спискам файлов HF API и документации движков. Поручение: сначала попробовать квантизованную модель. Состояние исследования альтернатив сохранено ниже; выбранный EXL3 после этого скачан и успешно запущен, см. [отчёт стенда](07-vast-exl3.md). FP8 уже является форматом пониженной точности; здесь ищем более компактные варианты.

**Итоговый выбор создателя, 2026-09-22:** EXL3 2.9 bpw от dealignai на одном узле Vast.ai; фактически арендованы и проверены 2×H200 (B200 были первоначальным планом). [Актуальный план](04-webinar.md). Q2 сохранён как альтернатива.

## 1. Q2 от pyrodog — сохранённая альтернатива

- [Карточка и инструкция](https://huggingface.co/pyrodog/DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2).
- [Файлы закреплённой ревизии](https://huggingface.co/pyrodog/DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2/tree/5789b4e1590673b3f596613b7e14cd87ad0e775b).
- [Прямая загрузка GGUF](https://huggingface.co/pyrodog/DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2/resolve/5789b4e1590673b3f596613b7e14cd87ad0e775b/DeepSeek-V4.1-Flash-UNCENSORED-Q2-bootstrap.gguf).

По описанию автора, это конверсия **нашего исходного dealignai FP8 checkpoint**, revision `d61c59ea5e514e25d305b5850e8a432f7a9969f2`, без дополнительного обучения. Один файл: **365713686528 байт — 365,7 GB / 340,6 GiB**, включая Engram. Размер и SHA256 получены из HF API; локальной проверки полного файла ещё нет.

Особенности: специальный GGUF для **DwarfStar**, без vision и DSpark; bootstrap-квантование без activation imatrix. Автор сообщает о запуске на Mac с 128 GB и SSD streaming. Эти результаты не подтверждают работу на нашем сервере.

[Движок DwarfStar](https://github.com/antirez/ds4), [инструкция для DGX Spark](https://github.com/antirez/ds4/blob/0aaea5a238fb41a35106a551e73c8409dfb751ac/docs/DGX_SPARK.md), [описание моделей](https://github.com/antirez/ds4/blob/0aaea5a238fb41a35106a551e73c8409dfb751ac/docs/MODELS.md).

Документация движка описывает V4.1 Q2 text inference на одном DGX Spark 128 GB с CUDA и SSD streaming. Этот вариант рассматривался первоначально; создатель выбрал EXL3 на 2×B200. Совместимость именно файла pyrodog с этой CUDA-сборкой пока является предположением для проверки. Поддержку других GPU нельзя выводить из одного наличия CUDA.

Для планирования закладываем минимум 500 GB свободного локального SSD, лучше 1 TB с запасом. Это наш запас под GGUF, сборку и кэши, не измеренный минимум движка. NFS не считаем заменой быстрому локальному SSD для этого маршрута.

## 2. EXL3 2.9 bpw от dealignai — вариант авторов модификации

- [Карточка и запуск](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-EXL3-2.9bpw).
- [Файлы закреплённой ревизии](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-EXL3-2.9bpw/tree/8a27b35fc5b145fa05ee965c7d7b243b047915f7).
- [Комплект запуска MiaAI-Lab](https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-EXL3-2x-DGX-Sparks/tree/6f7d1590ad49a2b8995188e45d7b9db31e677452).

Авторы публикуют квантизованную abliterated V4.1 с EXL3 2.9 bpw и описывают запуск на **2×DGX Spark, соединённых CX7**. Это релиз той же команды, но побайтовую цепочку преобразования нашей FP8-ревизии отдельно не проверяли.

HF API: 39 safetensors, **210600499333 байт — 210,6 GB / 196,1 GiB**. **Engram в этот размер не входит.** Нужны дополнительно shards 47 и 48 базовой модели, индекс и config:

- [Базовая модель, закреплённая ревизия](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/tree/dba1be0a40aa45a94ad051997016db3960a90277).
- [Shard 47](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/resolve/dba1be0a40aa45a94ad051997016db3960a90277/model-00047-of-00048.safetensors).
- [Shard 48](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/resolve/dba1be0a40aa45a94ad051997016db3960a90277/model-00048-of-00048.safetensors).

По HF API эти два шарда занимают ещё **203073077576 байт**. Итого веса и Engram — около **413,7 GB на диске**, до образов и кэшей. Это не требование к VRAM. MiaAI использует специальный vLLM/ExLlamaV3 overlay для GB10/ARM64 и чтение Engram с диска. Готовность исходного Spark-образа для H100/x86_64 не установлена; отдельно проверен native vLLM/ExLlamaV3 на x86_64 H200 с адаптациями из [runbook](07-vast-exl3.md).

## 3. MLX от OrcaRouter — отдельная модификация

[Карточка](https://huggingface.co/orcarouter/DeepSeek-V4.1-Flash-Uncensored-MLX), [2bit](https://huggingface.co/orcarouter/DeepSeek-V4.1-Flash-Uncensored-MLX/tree/main/2bit), [3bit](https://huggingface.co/orcarouter/DeepSeek-V4.1-Flash-Uncensored-MLX/tree/main/3bit), [4bit](https://huggingface.co/orcarouter/DeepSeek-V4.1-Flash-Uncensored-MLX/tree/main/4bit).

Карточка заявляет соответственно 212,2 / 364,3 / 458,7 GB и Mac с 256 / 512 / 512 GB RAM. Это заявления издателя, размеры файлов здесь не пересчитаны. Происхождение именно от dealignai не подтверждено, поэтому не считаем эквивалентом модели поста. Файлы gated: требуется принятие условий доступа. Для первой попытки на NVIDIA-сервере не выбираем.

## Что отсеяли

- [Solstice GGUF](https://huggingface.co/Solstice-AI/DeepSeek-V4.1-Flash-UNCENSORED-HyperSynapse-SAS-GGUF): HF API не показал ни одного GGUF/safetensors; одна карточка не является готовой моделью.
- [com-kotobalabs EXL3 2.0bpw](https://huggingface.co/com-kotobalabs/Deepseek-v4.1-Flash-Uncensored-EXL3-2.0bpw): 48 safetensors, около 358,1 GB, но README описывает FP8. Формат и маршрут запуска требуют отдельной проверки.
- [audreyt Q2 GGUF](https://huggingface.co/audreyt/DeepSeek-V4.1-Flash-Abliterated-GGUF): другая линия ablation, от s-zaizen; не конверсия dealignai.

## Итог исследования и воспроизведение

Выбранный EXL3 запущен на 2×H200. Все 39 EXL3 и два Engram-файла прошли полный локальный SHA256 на сервере; [отчёт](../deploy/weights-verified.json). Другие варианты выше не разворачивались. Установка, patches и ограничения — в [отчёте H200](07-vast-exl3.md); перенос на новый сервер — в [общем runbook](08-portable-deployment.md).

Метаданные кандидатов, SHA256 от HF и revisions сохранены в [quantized-manifest.json](../quantized-manifest.json). Нельзя просто заменить имя модели в старом FP8 `scripts/serve.sh`, чтобы получить EXL3 runtime.
