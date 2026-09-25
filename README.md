# Развёртывание DeepSeek: переносимый комплект

Инструкции и инструменты по опыту запуска DeepSeek V4.1 Flash UNCENSORED.
Обновлено **2026-09-25**. Контекст вебинара — [пост RoboFuture №171](https://t.me/robofuture/171).
**Стенд Vast 2×H200 остановлен, диск отключён; следующий запуск там — с чистой установки.** 2026-09-23 FP8-версия запущена на ноутбуке Cloud.ru 4×H100 (TP=4, графы, DSpark); EXL3 там же остался на диске как запасной вариант. 2026-09-24 та же FP8-версия запущена на ноутбуке 8×H100 на всех картах: TP=8, окно 1048576. Следующий сервер и формат модели могут отличаться: адреса и размеры действующих стендов не являются общими требованиями.

## Какую модель мы запускали

[`dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8`](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-UNCENSORED-FP8), revision `d61c59ea5e514e25d305b5850e8a432f7a9969f2` ([manifest](model-manifest.json)). Это `deepseek-ai/DeepSeek-V4.1-Flash` со снятыми отказами, в том же формате и того же размера. Числа ниже пересчитаны 2026-09-25 по заголовкам всех 48 safetensors на сервере ([метод и таблица](reports/2026-09-25/model-size/README.md)).

| | Значение |
|---|---|
| **Параметров всего** | **763,2 млрд** — совпадает с «Model size 763B params» на Hugging Face |
| Routed experts | 557,2 млрд: 384 эксперта в каждом из 40 слоёв и в слое MTP, FP4 (MXFP4) |
| Таблицы Engram (n-gram память) | 196,6 млрд, FP8, 202,8 GB = 188,8 GiB. Модель выбирает из них строки, а не умножает на них. vLLM держит их в pinned RAM, а не в VRAM |
| Остальное | 9,4 млрд: attention 5,1, общий эксперт 1,5, embedding и head 1,3, MTP/DSpark 0,6 (плюс эксперты в строке выше), vision 0,4, router, нормы |
| **Активно на токен** | **около 16 млрд** по нашему расчёту из config: top-6 из 384 экспертов (8,5 млрд) плюс общий эксперт, attention и head (около 7 млрд). Строки Engram не считаются. Карточка пишет «8B/16B active» |
| Формат | FP8 E4M3 блоками 32×32 с масштабами E8M0; эксперты MXFP4 (FP4, блок 32); нормы и часть проекций BF16. У базового `deepseek-ai/DeepSeek-V4.1-Flash` на HF те же типы и то же число параметров: это его исходный формат, а не пересжатие dealignai |
| На диске | 510,3 GB = 475,2 GiB; без таблиц Engram — 307,5 GB = 286,4 GiB (это нужно разместить в VRAM) |
| Архитектура | `DeepseekV41ForCausalLM`: 40 слоёв, hidden 5120, словарь 129 280, окно до 1 048 576, vision tower (мы запускаем `--language-model-only`) |

Карточка модели называет «552B backbone». Так её авторы, видимо, считают модель без Engram. Наш подсчёт без Engram — 566,6 млрд; как получено 552, карточка не поясняет. Масштабы квантования (23,6 млрд значений E8M0) в число параметров не входят.

EXL3-вариант из [docs/06](docs/06-quantized-models.md) — та же модель: эксперты пересжаты до 2,9 бит, таблицы Engram взяты из базовой модели без изменений.

## Начать здесь

**FP8 на vLLM и замер скорости** — готовый скил [skills/ds4-fp8-vllm](skills/ds4-fp8-vllm/SKILL.md): конфиг, запуск, фиксированный замер. **Клиент free-code** (сборка, туннель, команда `free-code`, `free-code --yolo`, проверка) — скил [skills/free-code-deepseek](skills/free-code-deepseek/SKILL.md). Исходники free-code: [gitverse.ru/krestnikov/free_code](https://gitverse.ru/krestnikov/free_code) (clone: `https://gitverse.ru/krestnikov/free_code.git`). Скилы в `skills/` написаны для любого агента, не только для одного харнесса.

Для повторения EXL3 начните с [чистой установки](docs/11-live-cold-start.md): один профиль и последовательные стадии `ops/exl3.sh`. Длительность вебинара не определяет порядок проверок.

1. [AGENTS.md](AGENTS.md) — правила для следующего агента. `CLAUDE.md` ссылается на него.
2. [Переносимое развёртывание](docs/08-portable-deployment.md) — выбор EXL3 / FP8 / BF16, ресурсы, веса, установка, запуск, приёмка.
3. [Все найденные ошибки и инсайты](docs/09-lessons-and-errors.md) — симптомы, причины, исправления, ограничения переноса.
   Для **4×H100 80GB** сразу [рецепт](docs/12-h100-4x80.md), не H200-preflight.
4. [Скорость: CUDA graphs, DSpark, выбор схемы под железо](docs/13-speed.md) — на 4×H100 без этого модель работала в 5 раз медленнее.
5. [API, Model UI, free-code и обслуживание](docs/10-clients-and-operations.md).
6. [План вебинара](docs/04-webinar.md) — **целевое демо: FP8 на 4×H100, штатный vLLM**; EXL3 — запасной вариант для 2×H200.

## Что подтверждено

| Маршрут | Статус |
|---|---|
| EXL3 2.9 bpw dealignai, 2×H200 Vast, vLLM/ExLlamaV3 | Запущен 2026-09-22: 41 SHA256, kernel tests, API, SSE, tool cycle, перезапуск, Model UI, free-code Read |
| Тот же EXL3, 4×H100 80GB, ноутбук Cloud.ru | Запущен 2026-09-23 на всех четырёх картах: TP=2 × DP=2 + EP, CUDA graphs, DSpark k=3, окно 1048576. Smoke 3 PASS; 58 токенов/с в один поток, 254 в сумме при 8 запросах ([замеры](docs/13-speed.md)). Рецепт — [docs/12](docs/12-h100-4x80.md). Раньше: две карты + offload, 9,6 токенов/с, `/v1/models` и короткий free-code. Kernel parity этого узла отдельно не снимался; free-code на быстром профиле не проверен |
| FP8 dealignai, 4×H100 80GB, штатный vLLM 0.30.0 | Запущен 2026-09-23 на том же ноутбуке: TP=4 + EP, CUDA graphs, DSpark, окно 65536. 48 SHA256, smoke 3 PASS; 206 токенов/с в один поток, 644 в сумме при 4 ([docs/13](docs/13-speed.md)). Отдельный venv без EXL3-патчей |
| Тот же FP8 по скилу [ds4-fp8-vllm](skills/ds4-fp8-vllm/SKILL.md), с пустого диска | 2026-09-24, ноутбук Cloud.ru 8×H100: venv совпал с эталонным freeze, 48 SHA256, smoke 3 PASS. Все 8 карт (TP=8 + EP, 32 запроса, окно 1048576): 201–214 токенов/с в один поток, 1152 в сумме при 8, 2697 при 32; спрятанный код найден в промпте на 1 033 152 токена (prefill 253 с). На 4 картах там же 199 и 641 при 4 ([отчёты](reports/2026-09-24/fp8/)). Нужен согласованный CUDA toolkit 13.0 — скрипт в скиле |
| Клиент free-code по скилу [free-code-deepseek](skills/free-code-deepseek/SKILL.md) | 2026-09-25, macOS arm64 → Cloud.ru 8×H100 FP8 через exec-мост: сборка `2.1.251-free-code.1` (commit `a89531f`) с нуля, профиль на окно 1048576, `verify.py`: Read, Bash под встроенным `--yolo`, отказ без него — 5/5 PASS ([отчёты](reports/2026-09-25/free-code/)). Linux-клиент и systemd не проверялись |
| FP8 dealignai, 8×H100, source SGLang | Исторически проверен 2026-09-14; не доказательство работоспособности нового Docker-рецепта |
| Новые portable scripts/profiles | Локальные проверки в [отчёте](reports/validation.md); чистая GPU-переустановка ими ещё не выполнена |
| BF16/FP16, другие GPU/модели | Порядок выбора и скелет профиля; готовый рабочий запуск не заявляется |

FP8 — тоже пониженная точность. «Полноценную модель» сначала определить по checkpoint metadata; нельзя получить её простой заменой `--quantization`.

## Готовые инструменты

| Файл | Что делает |
|---|---|
| [ops/exl3.sh](ops/exl3.sh) | Стадии preflight → deps → install/download → verify → serve → smoke для записанного H200-профиля |
| [ops/inspect.sh](ops/inspect.sh) | Read-only инвентаризация GPU, CPU/cgroup, диска, toolkit и портов |
| [ops/weights.py](ops/weights.py) | Закрепляет HF revision, скачивает snapshot, проверяет полные SHA256 |
| [ops/run-model.sh](ops/run-model.sh) | Запускает vLLM или SGLang из доверенного профиля; есть `--dry-run` |
| [profiles/](profiles/) | Начальные EXL3, FP8, native-профили и шаблоны Supervisor/systemd |
| [deploy/install-runtime.sh](deploy/install-runtime.sh) | Специфичный EXL3 adapter для pinned vLLM 0.30.0; root/toolkit/arch задаются явно |
| [deploy/patch-fast-path.py](deploy/patch-fast-path.py) | Патчи для CUDA graphs и TP×DP+EP на vLLM 0.30.0; проверяет исходники, повторный запуск ничего не меняет, `--check` без записи |
| [ops/smoke.py](ops/smoke.py) | Реальная генерация, SSE, необязательный tool/file round trip |
| [ops/bench-decode.py](ops/bench-decode.py) | Замер TTFT и токенов/с в 1..N потоков с фиксированной длиной ответа |
| [ops/long-context.py](ops/long-context.py) | Проверка окна: код в тексте нужной длины, время prefill и найден ли ответ |
| [ops/tunnel.sh](ops/tunnel.sh) | SSH loopback tunnel с проверкой host key |
| [ops/ssh-exec-tunnel.py](ops/ssh-exec-tunnel.py), [ops/tcpbridge.py](ops/tcpbridge.py) | Мост через шлюз, который не пропускает `ssh -L` (Cloud.ru Jupyter): каждое соединение — SSH-команда |
| [ops/configure-free-code.py](ops/configure-free-code.py) | Отдельный профиль и launcher для существующего бинарника |
| [skills/free-code-deepseek/scripts/](skills/free-code-deepseek/scripts/) | `tunnel-agent.py` — туннель как LaunchAgent/systemd `--user`; `verify.py` — сквозная проверка клиента: Read, Bash под `--yolo`, отказ без него |
| [ops/configure-model-ui.py](ops/configure-model-ui.py) | Preview/apply настроек штатного Vast Model UI, с сохранением auth |

Быстрый старт: скопировать подходящий `profiles/*.env.example`, заполнить фактические пути/ресурсы, установить **совместимый** runtime, скачать и проверить веса, выполнить dry-run, запустить и пройти smoke. Полные команды — в [runbook](docs/08-portable-deployment.md). Новый профиль не должен содержать токены.

```bash
python3 -m unittest discover -s tests -v
bash ops/run-model.sh profiles/exl3-h200.env.example --dry-run
bash ops/run-model.sh profiles/fp8-sglang.env.example --dry-run
```

## История, источники и доказательства

- [Контекст и исходные pins FP8](docs/01-context.md).
- [Требования исходного FP8-стенда](docs/02-server.md), [старый Docker-runbook](docs/03-runbook.md), [его диагностика](docs/05-troubleshooting.md).
- [Ссылки на квантования](docs/06-quantized-models.md).
- [Отчёт Vast/H200](docs/07-vast-exl3.md): версии, patches, внутренние порты и приёмка. Адреса аренды в комплект не входят.
- [FP8 manifest](model-manifest.json), [EXL3/Engram manifest](quantized-manifest.json), [фактическая проверка 41 файла](deploy/weights-verified.json).
- `deploy/serve-exl3.sh`, `deploy/ds41-exl3.conf` — сохранённый профиль стенда; `scripts/` — прежний FP8 Docker-маршрут. Новую аренду запускать после адаптации, не копировать эти файлы вслепую.

Веса, секреты и адреса аренды в комплект не включены. Каталог не является git-репозиторием.
