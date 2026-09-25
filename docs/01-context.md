# Контекст и источники

## Что берём из поста

[Пост №171](https://t.me/robofuture/171) прочитан 2026-09-22 через публичный Telegram embed. Он описывает опыт автора с модифицированной моделью и агентским клиентом. Для вебинара воспроизводим цепочку «арендованный сервер → локальный API → клиент → выполненная тестовая задача».

Ссылка в посте ведёт на `dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8`. Слова «края нет» и отсутствие отказов в личных экспериментах — впечатления автора, а не гарантия качества. Проценты MMLU в посте относятся к измерениям авторов модификации. Они не заменяют нашу оценку. Истории про атаки и снятие лицензий не нужны для проверки установки; для демонстрации достаточно собственного учебного проекта.

## Зафиксированные компоненты

| Компонент | Значение | Основание |
|---|---|---|
| Веса | dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8 | Ссылка из поста |
| HF revision | d61c59ea5e514e25d305b5850e8a432f7a9969f2 | HF API, проверка 2026-09-22 |
| Safetensors | 48 файлов, 510296708312 байт (~510,3 GB / 475,3 GiB) | Сумма размеров HF API |
| Docker | lmsysorg/sglang:dev-dsv41 | Preview, указанный разработчиками модификации |
| Digest индекса образа | sha256:4a5d132a06a77c8331e15845f2e925adc788b00105097ad55409afa3f4fa4860 | Docker Hub API, 2026-09-22 |
| Историческая сборка SGLang | 5d42bf1f12a9e0c675be316693058d03e3df8cf2 | Внутренняя запись успешного запуска 2026-09-14 |

Digest фиксирует содержимое Docker-образа, но не означает, что в нём именно историческая сборка SGLang. Её соответствие не установлено. `scripts/config.sh` содержит параметры нового маршрута; `model-manifest.json` — размеры и SHA256 весов из HF API. Хеши получены от хостинга, это не независимая подпись автора.

## Источники для перепроверки

- [Карточка модификации](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8): запуск и заявления авторов; preview-инструкции могут меняться.
- [Зафиксированная ревизия](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8/tree/d61c59ea5e514e25d305b5850e8a432f7a9969f2): содержимое скачиваемого checkpoint.
- [HF API ревизии](https://huggingface.co/api/models/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8/revision/d61c59ea5e514e25d305b5850e8a432f7a9969f2?blobs=true): манифест.
- [SGLang, исторический commit](https://github.com/sgl-project/sglang/tree/5d42bf1f12a9e0c675be316693058d03e3df8cf2): исходники и объявленные параметры.
- [Docker Hub API](https://hub.docker.com/v2/repositories/lmsysorg/sglang/tags/dev-dsv41): digest на дату подготовки.
- [Hugging Face: download](https://huggingface.co/docs/huggingface_hub/guides/download): загрузка с `revision` и `local_dir`.
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html): подготовка GPU runtime, если его нет в шаблоне провайдера.
- [Docker: ограничения ресурсов](https://docs.docker.com/engine/containers/resource_constraints/): память контейнера и поведение OOM.

Проверки 2026-09-14: 8×H100, генерация, streaming, tool calls и чтение файла через free-code. Поздний EXL3-стенд описан в `docs/07-vast-exl3.md`.
