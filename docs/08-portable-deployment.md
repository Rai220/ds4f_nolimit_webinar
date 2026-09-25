# Переносимый runbook: от нового сервера до проверенного клиента

Обновлено 2026-09-22. Версии и размеры проверенного стенда — в [отчёте Vast](07-vast-exl3.md). Здесь порядок принятия решений. Скрипты не арендуют сервер, не удаляют веса, не останавливают чужой сервис и не меняют драйвер.

## Самый быстрый следующий запуск

Сервер остановлен, диск отключён владельцем. Для следующего запуска не предполагаются сохранённые веса, venv или cache: основной маршрут — [чистая установка](11-live-cold-start.md). Варианты с сохранённым диском ниже применимы только при его фактическом наличии.

| Ситуация | Кратчайший проверяемый путь |
|---|---|
| Тот же остановленный контейнер, filesystem сохранился | Сверить реквизиты → проверить веса/venv/cache на месте → existing service start/health → smoke. Не переустанавливать и не скачивать повторно |
| Новый узел той же архитектуры с доступным томом | Инвентаризация → подключить правильный том → сверить версии/профиль → проверить kernels → запуск и smoke |
| Новый узел / другие GPU | Сначала совместимость toolkit/runtime/kernels; затем перенос весов или pinned download. Нельзя переносить старые cubins как гарантию |
| Другой checkpoint/формат | Новый manifest и план памяти → правильный loader/runtime → отдельная приёмка; использовать общие ops, а не EXL3 patches |

До включения GPU можно подготовить profiles, файлы клиента, pins, скрипты и план теста. На машине с сохранёнными **проверенными и неизменёнными** весами каждый restart не требует повторного чтения сотен GB; hash-аудит обязателен после новой загрузки/переноса или подозрения на повреждение. При исправном cold start дождаться JIT, не перезапускать его по кругу.

## 1. Выбрать маршрут по фактической модели

| Формат / маршрут | Состояние знаний | Что переиспользовать |
|---|---|---|
| dealignai EXL3 2.9 bpw, V4.1 | Реально запущен на 2×H200 и отдельно на 4×H100 80GB | H200 — [чистая установка](11-live-cold-start.md). 4×H100 — [отдельный рецепт](12-h100-4x80.md): TP=2 × DP=2 + EP, CUDA graphs, DSpark, окно 1048576. Не прогонять H200-preflight. Скорость и выбор схемы под другое железо — [docs/13](13-speed.md) |
| dealignai FP8, V4.1 | Исторический успешный source build SGLang на 8×H100, 2026-09-14 | Совместимую SGLang-ревизию, парсеры, CPU Engram; новый Docker-рецепт ещё не прошёл чистую GPU-репетицию |
| BF16/FP16 / другие полные веса | Здесь не разворачивались | Инвентаризацию, manifest, API-тесты, transport, менеджер процессов. Runtime и память выбирать заново |
| GGUF/DwarfStar, MLX | Найдены ссылки, запуск здесь не проверялся | Только [исследование вариантов](06-quantized-models.md); не использовать EXL3/SGLang-команду |

«Полная модель» не определяет dtype. FP8 уже пониженная точность; отсутствие EXL3 не означает BF16. Проверить `config.json`, `quantization_config`, `architectures`, dtype и индекс тензоров. Нельзя получить BF16-качество из EXL3, переименовав каталог или удалив `--quantization`. Для другого checkpoint нужен его собственный manifest и вся конфигурация/tokenizer/chat template.

Даже одинаковое семейство требует точной версии: V4 и V4.1, Flash и другой размер — разные конфигурации. Не заменять названия парсеров по сходству. В проверенном vLLM: `deepseek_v41`; в SGLang: reasoning `deepseek-v41`, tools `deepseekv41`.

## 2. Инвентаризация до большой загрузки

Прочитать руководство провайдера. На Vast контейнере — `/etc/vast-agents-guide.md`; не останавливать caddy, instance_portal, tunnel_manager. Root в контейнере не даёт права менять host driver, kernel или системные лимиты.

```bash
# На новом сервере из каталога комплекта. Ничего не изменяет.
bash ops/inspect.sh /ПУТЬ/К/ТОМУ > inventory.txt
```

Сверить:

- Фактические GPU, свободную VRAM, процессы, topology и CPU architecture. Шаблон назывался B200, фактически оказались H200; это выяснилось только через SSH.
- RAM именно cgroup, не только `free -h` хоста. Для текущего контейнера это около 967 GiB против 2 TiB хостовой RAM. CPU quota тоже может быть меньше видимых ядер.
- `nvidia-smi` сообщает максимальную CUDA-версию драйвера, `nvcc --version` — установленный toolkit. На H200 были driver 590.48.01 / advertised CUDA 13.1, toolkit 13.0, Torch cu130.
- Свободное место, тип тома и политику сохранности. `/workspace` — имя пути, не гарантия persistent storage. На текущем Vast recycle/destroy стирает overlay, stop/start его сохраняет по руководству провайдера.
- Docker доступен не везде. В готовом Vast-контейнере использовали отдельный venv и Supervisor. Исторический Jupyter-контейнер Cloud.ru потребовал собственный toolkit. На полноценной VM возможны Docker или systemd.
- Порты: runtime, UI backend, Caddy edge, host mapped port и local tunnel port — разные сущности. Не занимать серверный 8080 автоматически: на текущем образе это Jupyter.

Доступ подтвердить командой по SSH и host key, не открытым TCP-портом. Не делать широкое сканирование. Если GPU заняты неизвестным сервисом, сначала выяснить владельца/назначение; разрешение заменить Qwen на прошлом стенде не переносится на чужой новый сервер.

## 3. Оценить память и диск

**Диск и GPU RAM не равны.** Общий бюджет включает веса, Engram, KV cache, активации/рабочие буферы, CUDA graph, аллокатор и запас. Для MoE важны все размещённые эксперты, а не только число активных параметров. Для tensor parallel считать не только сумму VRAM: реплицируемые части и неравномерность шардирования тоже занимают память.

На проверенном EXL3:

- 39 файлов EXL3 — 210 600 499 333 байт.
- Отдельные Engram 47/48 — 203 073 077 576 байт. Полный набор около 413,7 GB.
- Загруженные веса — около 95,94 GiB на GPU. Фактическая аллокация с KV/cache при 64K — около 131307 MiB на GPU, измерено 2026-09-22. Это не гарантированный расход на другом runtime.
- File-backed Engram использует row-store cache; `DSV41_CACHE_GIB=8` делится на два слоя и два TP rank: по 2 GiB, не по 8 GiB каждому.
- `gpu-memory-utilization` резервирует кэш, поэтому почти заполненная VRAM в idle не означает утечку. Большое расчётное число KV-токенов не доказывает приёмку полного контекста.

FP8 snapshot — около 510,3 GB, включая его собственный состав Engram. Не добавлять к нему EXL3 Engram автоматически. Исторические 8×H100 — проверенная конфигурация, не минимум. Для BF16/FP16 пересчитать по реальным тензорам: нельзя просто умножить итоговый FP8-файл на два, поскольку dtype различных компонент и упаковка могут отличаться.

Закладывать диск под checkpoint, образы/venv, build и JIT-кэши. `pip`/`uv`/HF могут создавать дополнительные копии; размещение каждого cache задать явно. Сетевой том подходит для хранения, но случайное чтение file-backed Engram требует проверки задержек; NFS не объявлять эквивалентом локального NVMe.

## 4. Закрепить модель и проверить веса

`ops/weights.py` понимает оба сохранённых manifest. Для загрузки/получения нового manifest нужен `huggingface_hub`; проверка SHA256 использует только Python stdlib. Устанавливать зависимость в выбранный venv, не в чужое системное окружение.

```bash
# Новый checkpoint: сначала метаданные, без загрузки сотен GB.
python ops/weights.py pin --repo OWNER/MODEL --revision main --output new-model-manifest.json
```

`main` разрешается в точный commit SHA. Просмотреть manifest: repo может содержать сразу несколько квантований/вариантов. Утилита pin перечисляет weight-файлы всех вариантов и не выбирает подходящий автоматически. Для такого репозитория подготовить отдельный список нужных файлов/подкаталога, проверив совместимость и пути. По умолчанию `download` получает полный snapshot; это намеренно не автоматический фильтр альтернатив.

Для выбранного EXL3:

```bash
export DATA_ROOT=/srv/ds41-exl3    # заменить на свой большой том
export EXL3_REPO=dealignai/DeepSeek-V4.1-Flash-UNCENSORED-EXL3-2.9bpw
python ops/weights.py download --manifest quantized-manifest.json --repo "$EXL3_REPO" --dest "$DATA_ROOT/model"
python ops/weights.py download --manifest quantized-manifest.json --engram --dest "$DATA_ROOT/engram"
mkdir -p "$DATA_ROOT/reports"
python ops/weights.py verify --manifest quantized-manifest.json --repo "$EXL3_REPO" --dest "$DATA_ROOT/model" --report "$DATA_ROOT/reports/model-sha256.json"
python ops/weights.py verify --manifest quantized-manifest.json --engram --dest "$DATA_ROOT/engram" --report "$DATA_ROOT/reports/engram-sha256.json"
```

Для сохранённого FP8: те же download/verify с `--manifest model-manifest.json`, без `--repo` и `--engram`. Для BF16 — свой новый manifest.

Проверка читает все веса целиком. Проверка только размера/header/index не равна SHA256. Файлы config/tokenizer загружаются из pinned snapshot; эти утилиты не заявляют независимый hash-аудит всех support-файлов. SHA256 от HF — проверка целостности относительно хостинга, не независимая подпись автора. Если требуется `trust_remote_code`, отдельно изучить код выбранной ревизии.

При обрыве повторить download с той же revision/destination. При hash mismatch остановиться и адресно исправить повреждённый файл, не начинать генерацию. HF-токен, если нужен, загружать в окружение/хранилище, не в профиль и не в аргументы команд.

## 5A. EXL3: подготовить runtime

Этот адаптер предназначен **только** для закреплённого сочетания V4.1 EXL3 и vLLM 0.30.0. Он не обещает поддержку произвольной модели/GPU. Исходный MiaAI Docker рассчитан на ARM64/GB10 и двухузловой Spark; на x86_64 H200 использовали native venv.

```bash
# Значения выбрать после инвентаризации. Требуются git, g++, uv, toolkit.
export DS41_ROOT=/srv/ds41-exl3
export UV_BIN=uv                      # на прежнем образе /opt/sglang/bin/uv
export CUDA_HOME=/usr/local/cuda      # реальный путь к nvcc
export TORCH_CUDA_ARCH_LIST=9.0a       # ТОЛЬКО для проверенного H200; другую GPU определить отдельно
export MAX_JOBS=16                    # ограничить по cgroup CPU/RAM
export OVERLAY_DIR="$DS41_ROOT/overlay"
bash deploy/install-runtime.sh
```

Installer требует явные root/toolkit/architecture, создаёт venv, закрепляет vLLM, ExLlamaV3 и MiaAI commits. Путь установки допускает буквы, цифры, `/._-`; это ограничение механизма замены путей в upstream patch. Не запускать installer поверх live/shared venv. Для изменения версии создать отдельное окружение.

Что он делает дополнительно:

1. Переносит module path `deepseek_v4_1` → `deepseek_v41`, регистрирует EXL3 в quantization registry и ModelConfig overrides.
2. Применяет авторские patches для packed names/lm_head, EXL3 линейных проекций и secondary Engram; нулевое число правок отдельного upstream patch допустимо лишь после чтения конкретного кода, не как общее правило успеха.
3. Компилирует `librow_store.so`, подключает file-backed Engram к common и NVIDIA subclass; поддерживает новый `dp_shared_memory=False`, явно отвергает неподдерживаемый shared-DP.
4. Импортирует `engram_head_shard_rank` из NVIDIA-модуля; для добавочного install использует импортируемый `engram_file_backend`, а не несуществующий в `sys.modules` dynamic alias.
5. Устанавливает `aux_stream_list=None` для общих EXL3 kernel locks. Переменная окружения без patch не исправляет deadlock.
6. Для переносимого toolkit добавляет поиск libcudart через `CUDA_HOME`. Эта новая переносимая ветка проверена локально на структуре исходников, на новой GPU ещё не испытана.

Сборка должна содержать native cubins для фактической GPU и `exl3_moe`; импорт сам по себе не доказывает исполнение. На H200 прошёл авторский `test_exl3_overlay.py` с заменой только проверяемой архитектуры SM121 → SM90, включая GEMM/MoE/parity/CUDA graph; отдельно `test_engram_dequant.py`. Логи — `deploy/exl3-kernels.txt`, `deploy/engram-dequant.txt`. На новом узле повторить соответствующие тесты из закреплённого kit. Fat-grouped extension не входил в рабочий baseline.

## 5B. FP8 / BF16: отдельный runtime

Для FP8 есть [исторический Docker-runbook](03-runbook.md) с pinned digest и отдельный source commit SGLang `5d42bf1f12a9e0c675be316693058d03e3df8cf2`. Не утверждаем, что digest содержит тот же commit. Проверить `--help`, поддержку архитектуры, наличие parsers, weights loader и CUDA kernels выбранной сборки до загрузки модели. Если Docker отсутствует, использовать native venv по инструкции той ревизии, а не устанавливать вложенный Docker.

BF16/FP16 или другой полноценный checkpoint: проверить поддержку в выбранном движке и реальные dtype. Скелет `profiles/native-vllm.env.example` намеренно содержит незаполненные TP/context/model ID и не запускается как готовая DeepSeek-конфигурация. EXL3 patches, EXL3 engram override и EXL3 флаги туда не переносить. Если модель имеет собственный CPU offload, выбрать его по документации runtime и измерить стоимость transfers.

## 6. Первый запуск и готовность

```bash
cp profiles/exl3-h200.env.example /ABS/my-model.env
# Отредактировать ROOT, CUDA_HOME, PYTHONPATH, GPU/TP, context, ports.
bash ops/run-model.sh /ABS/my-model.env --dry-run
# Сверить с --help именно установленного runtime и ресурсами.
bash ops/run-model.sh /ABS/my-model.env
```

Для FP8 начать с `profiles/fp8-sglang.env.example`, для другого checkpoint — с соответствующего скелета. Профиль является **доверенным shell-кодом**, это не вход от модели/веб-страницы. `EXTRA_ARGS` — Bash-массив; не склеивать произвольную строку и `eval`.

Начать с одного запроса и eager, короткого достаточного контекста. На H200 стартовали с 8192, для free-code увеличили до 65536; полная ёмкость 64K отдельно не прогонялась. JIT занимает время, затем кешируется. Не объявлять сервер готовым по RUNNING, занятой VRAM или строке «weights loaded».

Eager — только для проверки корректности. Для работы включить CUDA graphs, затем DSpark: на 4×H100 это 11 → 35 → 58 токенов/с в один поток. Порядок, флаги и выбор TP/DP/EP под число и объём GPU — в [docs/13](13-speed.md). Для EXL3 графы требуют `deploy/patch-fast-path.py`, installer применяет его сам.

```bash
python3 ops/smoke.py --base-url http://127.0.0.1:18080/v1 \
  --model deepseek-v4.1-flash --no-thinking --tools
```

Для иной модели убрать `--no-thinking`, если template не поддерживает `enable_thinking`; выбрать достаточный `--max-tokens`. Tools проверять после выбора совместимого parser. Тест требует завершённого ответа и SSE `stop`/`[DONE]`, затем действительно читает фиксированный временный файл на стороне клиента. Он не исполняет произвольные сгенерированные команды.

## 7. Постоянный сервис, клиент и воспроизведение

После приёмки использовать существующий менеджер процессов: [Supervisor-шаблон](../profiles/supervisor.conf.example) для контейнера, [systemd-шаблон](../profiles/systemd.service.example) для обычной VM. Подставить абсолютные пути, создать logs/cache; не ставить второй supervisor рядом с уже существующим без причины. Шаблоны не устанавливают сервис сами.

Затем [подключить SSH/API/Model UI/free-code](10-clients-and-operations.md), сделать один управляемый перезапуск и повторить реальный запрос. Зафиксировать inventory, runtime freeze, commits, manifest/hash report, профиль, patches, readiness time, smoke и клиентский результат. Не сохранять все переменные среды или пользовательские запросы в публичный комплект.

Для следующего запуска передавать этот комплект, профиль конкретного узла и pinned manifest; веса переносить/кешировать отдельно. Полную переустановку делать лишь при необходимости. Новый хост с иными GPU/архитектурой требует новой проверки kernels; старый «PASS» не переносится автоматически.

Статус переносимых скриптов: локальные тесты/проверки описаны в `reports/validation.md`; EXL3 baseline на H200 реально работал, но установка **переносимой редакцией** на чистом сервере пока не выполнялась.
