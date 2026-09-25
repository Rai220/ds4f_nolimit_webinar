---
name: ds4-fp8-vllm
description: Поднять dealignai DeepSeek V4.1 Flash UNCENSORED FP8 на штатном vLLM 0.30.0 на всех GPU узла (4 или 8 H100/H200) и замерить скорость по фиксированному рецепту. Использовать, когда просят «подними ds4 / DeepSeek V4.1 Flash uncensored fp8 на vLLM», «замерь скорость», «сколько токенов в секунду», сравнить с эталоном 206 ток/с. Не для EXL3 (docs/11, docs/12) и не для BF16.
---

# DS4 UNCENSORED FP8 на vLLM: запуск и замер скорости

Самодостаточный рецепт для любого агента и человека. Готовые конфиги — [server-fp8-8gpu.env.example](server-fp8-8gpu.env.example) для 8 GPU и [server-fp8.env.example](server-fp8.env.example) для 4 GPU, запуск — [scripts/serve.sh](scripts/serve.sh), замер — [scripts/bench.sh](scripts/bench.sh). Пути даны от корня комплекта. Общие правила — [AGENTS.md](../../AGENTS.md), подробности и история — [docs/13](../../docs/13-speed.md).

## Правило замеров: только так

Число токенов в секунду сравнимо с эталоном, если выполнено всё:

1. Сервер занимает **все доступные GPU узла** и запущен из готового профиля под их число через `scripts/serve.sh`: 8 GPU — `server-fp8-8gpu.env.example`, 4 GPU — `server-fp8.env.example`. В копии профиля меняются только `ROOT` и `PORT`.
2. Замер сделан `scripts/bench.sh`. Скрипт сам:
   - сверяет командную строку работающего процесса с профилем и останавливается при расхождении;
   - гоняет `ops/smoke.py --tools` (3 PASS). Это и прогрев: первые запросы компилируют Triton/TileLang;
   - запускает `ops/bench-decode.py --parallel 1,1,4`: prompt по умолчанию (54 токена, русское эссе), 1024 токена ответа вместе с reasoning, `temperature 0`, `ignore_eos`;
   - сохраняет профиль, команду, версии, JSON и строки `SpecDecoding metrics`.
3. Первая строка `parallel=1` — прогрев. Цитировать вторую строку `parallel=1` и `parallel=4`, вместе с датой, GPU, версиями и именем профиля.

Всё остальное — **другой эксперимент**: другой TP, окно, eager, без DSpark, другой prompt, длина, температура, чужая нагрузка на тех же GPU. Такой отчёт класть в отдельную папку с понятным именем, отличие писать рядом с числом и не сравнивать его с эталоном напрямую. Выделение KV cache не доказывает, что полное окно работает.

## Эталон

| Дата | Узел | GPU | 1 поток | 4 потока, сумма | Отчёт |
|---|---|---|---:|---:|---|
| 2026-09-23 | Cloud.ru, ноутбук 4×H100 | 4×H100 80GB HBM3, NV18, driver 570.133.20 | 206 | 644 (164–169 на поток) | [reports/2026-09-23/fp8](../../reports/2026-09-23/fp8/) |
| 2026-09-24 | Cloud.ru, ноутбук 8×H100, 4-GPU профиль на GPU 0–3 | 8×H100 80GB HBM3, NV18, driver 570.133.20 | 199 (прогрев 204) | 641 (163–172 на поток) | [seq4](../../reports/2026-09-24/fp8/bench-20260924-fp8-dspark-seq4/) |
| 2026-09-24 | тот же, TP=8, `MAX_NUM_SEQS=4` | все 8 | 209 (прогрев 205) | 696 (178–188) | [tp8-seq4](../../reports/2026-09-24/fp8/bench-20260924-fp8-tp8-dspark-seq4/) |
| 2026-09-24 | тот же, TP=8, 32 запроса, окно 65536 | все 8 | 200–208 | 683 (175–183) | [tp8-seq32](../../reports/2026-09-24/fp8/bench-20260924-fp8-tp8-dspark-seq32/) |
| 2026-09-24 | тот же, **`server-fp8-8gpu.env.example`**: окно 1048576 | все 8 | 201–214 | 711 (181–185) | [tp8-seq32-1m](../../reports/2026-09-24/fp8/bench-20260924-fp8-tp8-dspark-seq32-1m/) |

Для 8-GPU профилей отдельно снята серия `ops/bench-decode.py --parallel 8,16,32` с тем же prompt и длиной. Окно 65536: 1165, 1864 и 2852 ток/с в сумме. Окно 1048576: 1152, 1806 и 2697 (147–157, 115–122 и 86–91 на поток). На одном потоке TP=8 даёт не больше нескольких процентов, это в пределах разброса между прогонами (199–214). Весь выигрыш восьми карт — в одновременных запросах и длине окна: KV вырос с 0,64 до 17,7 млн токенов.

**Полное окно проверено**, а не только выделено: `ops/long-context.py` прячет случайный код в середине случайного текста и спрашивает его. Код найден при 130 081, 520 991 и 1 033 152 токенах промпта; prefill занял 12,6 с, 68,7 с и 252,8 с (10,3 → 7,6 → 4,1 тыс. ток/с: indexer растёт квадратично). Это проверка извлечения факта, а не качества рассуждений на всём окне.

Версии: vLLM 0.30.0, torch 2.13.0+cu130, окружение — [pip-freeze](../../reports/2026-09-23/fp8/pip-freeze.txt). Вторая строка снята на узле, начатом с пустого диска: venv совпал с эталонным freeze полностью (196 пакетов), 48 SHA256 совпали. По ходу нашлись две ошибки toolkit (ниже, шаг 3); после исправления `install-cuda-toolkit.sh` отдельно прогнан в пустой каталог: тот же набор из 9 пакетов, тест компиляции и линковки пройден. Средняя длина принятого блока DSpark — 2,40–2,46. Время: установка runtime 11 минут, скачивание 11 минут 48 секунд (в среднем около 700 МБ/с), SHA256 6 минут, первый успешный старт с пустым кэшем FlashInfer 295 секунд.

## Что нужно от узла

Модель — 763,2 млрд параметров (как «763B» на Hugging Face): 557,2 млрд в экспертах MXFP4, 196,6 млрд в таблицах Engram FP8, остальное FP8/BF16. На токен активно около 16 млрд. Разбивка и расхождение с «552B» из карточки — в [README](../../README.md#какую-модель-мы-запускали). В VRAM идёт всё, кроме таблиц Engram: 286,4 GiB.

- 4 или 8 GPU Hopper или новее по 80 GB, NVLink; занимаются все карты узла. Веса — 73,4 GiB на карту при TP=4 и 37,6 GiB при TP=8. На 2×H200 FP8 не помещается: там EXL3.
- Драйвер с CUDA 13.0 и выше (`nvidia-smi`). Системный `nvcc` не обязателен: согласованный toolkit 13.0 ставится pip-пакетом (шаг 2).
- RAM от 256 GB: таблицы Engram (189 GiB) vLLM держит в pinned RAM.
- Локальный диск от 700 GB: checkpoint 475 GiB, venv 8 GB, кэши. Домашний каталог на ноутбуках часто общий NFS — туда не ставить.
- Доступ к Hugging Face и PyPI, Python 3.12, `uv`.

## Порядок

Проверять фактическое железо, а не имя шаблона: `bash ops/inspect.sh /ПУТЬ/К/ДИСКУ`. На Vast прочитать `/etc/vast-agents-guide.md`.

**1. Комплект на сервер.** `rsync` есть не везде, `tar` через SSH работает всегда:

```bash
COPYFILE_DISABLE=1 tar --exclude=./dist -czf - . | ssh -p PORT USER@HOST 'mkdir -p /var/tmp/ds41-webinar && tar xzf - -C /var/tmp/ds41-webinar'
```

**2. Runtime и веса — параллельно, в фоне.** Долгие команды запускать через `setsid nohup … > log`, статус проверять короткими командами: SSH через шлюзы обрывается. Если оболочка входа zsh, передавать скрипт так: `ssh … 'bash -s' <<'EOF'`.

```bash
KIT=/var/tmp/ds41-webinar ROOT=/var/tmp/ds41-fp8
export UV_CACHE_DIR=$ROOT/cache/uv UV_LINK_MODE=copy TMPDIR=$ROOT/cache/tmp HF_HOME=$ROOT/cache/hf
mkdir -p "$TMPDIR" "$ROOT/logs" "$ROOT/reports"
# Runtime: отдельный venv, все версии — из эталонного freeze. Результат совпадает с ним полностью.
uv venv --python 3.12 "$ROOT/venv"
uv pip install --python "$ROOT/venv/bin/python" \
  --constraint "$KIT/reports/2026-09-23/fp8/pip-freeze.txt" vllm==0.30.0 torch==2.13.0
# CUDA toolkit для JIT DeepGEMM и FlashInfer: nvcc, заголовки, curand, cuBLAS одной версии 13.0,
# отдельно от venv. Скрипт сам проверяет компиляцию и линковку так, как это делает JIT.
bash "$KIT/skills/ds4-fp8-vllm/scripts/install-cuda-toolkit.sh" "$ROOT"
# Веса: закреплённая ревизия, затем полный SHA256 всех 48 файлов. Без PASS не запускать.
uv venv --python 3.12 "$ROOT/download-venv"
uv pip install --python "$ROOT/download-venv/bin/python" huggingface_hub==1.30.0
cd "$KIT"
"$ROOT/download-venv/bin/python" ops/weights.py download --manifest model-manifest.json --dest "$ROOT/model"
"$ROOT/download-venv/bin/python" ops/weights.py verify --manifest model-manifest.json \
  --dest "$ROOT/model" --report "$ROOT/reports/model-sha256.json"
```

После установки — маленькая CUDA-операция на каждой карте: `"$ROOT/venv/bin/python" -c 'import torch; [print(i, (torch.ones(8, device=f"cuda:{i}") * 2).sum().item()) for i in range(torch.cuda.device_count())]'`.

`UV_LINK_MODE=copy` и свой `UV_CACHE_DIR` обязательны: установщик EXL3 правит файлы vLLM на месте, и через жёсткие ссылки uv эти правки попадают в чужие venv.

**3. Профиль.** Под фактическое число GPU из `nvidia-smi`, все карты узла:

```bash
cp skills/ds4-fp8-vllm/server-fp8-8gpu.env.example .local/server-fp8.env   # 8 GPU
# cp skills/ds4-fp8-vllm/server-fp8.env.example .local/server-fp8.env      # 4 GPU
chmod 600 .local/server-fp8.env    # поправить ROOT и PORT при необходимости
bash ops/run-model.sh "$PWD/.local/server-fp8.env" --dry-run
```

Другое число карт — новый профиль и отдельный замер: TP должен делить 64 головы attention и `o_groups` 8, то есть 1, 2, 4 или 8. Data parallel на штатном vLLM 0.30.0 не использовать: роутер DSv4 при DP читает `input_ids` не тех строк (метка `[dsv41-dp-input-ids]` в [docs/13](../../docs/13-speed.md)). Если карт больше восьми — две копии сервера на разных портах, а не DP.

`CUDA_HOME` в профиле указывает на `$ROOT/cuda13/nvidia/cu13` из шага 2. Почему не иначе (обе ошибки получены 2026-09-24):

- **Не** `nvidia/cu13` внутри venv: там `nvcc` 13.4 (его тянет зависимость без pin) рядом с заголовками runtime 13.0. CCCL требует совпадения версий, и старт падает на первом JIT DeepGEMM сразу после загрузки весов: `CUDA compiler and CUDA toolkit headers are incompatible`.
- **Не** минимальный `cuda-toolkit[nvcc,cccl]`: FlashInfer собирает sampling на прогревочном шаге и падает на `curand.h: No such file`, затем линкует `-L$CUDA_HOME/lib64 -lcudart`. Скрипт ставит curand и cuBLAS и делает ссылки `lib64` и `libcudart.so`. `-lcuda` берётся из драйвера узла (`libcuda.so`).

Свой CUDA 13.x toolkit узла подходит, если в нём `bin/nvcc`, заголовки той же версии, curand и cuBLAS.

JIT-кэши FlashInfer, Triton, TileLang и драйвера по умолчанию пишутся в `$HOME`. На ноутбуках Cloud.ru это один NFS-home для нескольких узлов с разными toolkit: наш запуск пересобирал там модуль FlashInfer, собранный соседним узлом. Профиль переносит их в `$ROOT/cache`.

**4. Запуск.**

```bash
bash skills/ds4-fp8-vllm/scripts/serve.sh "$PWD/.local/server-fp8.env" /var/tmp/ds41-fp8/logs/server.log
```

Скрипт отказывается стартовать, если порт занят или на выбранных GPU уже есть память, и ждёт `/v1/models`. Если сервер упал при старте, скрипт печатает хвост лога и выходит с ошибкой. Признаки нормального старта в логе: `Using 'MARLIN' Mxfp4 MoE backend`, `Model loading took 73.37 GiB`, `Graph capturing finished`, `GPU KV cache size: 639,692 tokens`, `Application startup complete`. Готовность — около 2 минут при прогретых кэшах; первый старт на новом узле около 5 минут: FlashInfer и другие JIT собирают модули.

**5. Замер.**

```bash
bash skills/ds4-fp8-vllm/scripts/bench.sh "$PWD/.local/server-fp8.env" \
  /var/tmp/ds41-fp8/logs/server.log /var/tmp/ds41-fp8/reports/bench-$(date +%Y%m%d-%H%M)
```

Окно проверять отдельно, на длинах, которые реально нужны, до полного окна включительно:

```bash
python3 ops/long-context.py --model deepseek-v4.1-flash --tokens 131072,524288,1040000 \
  --json /var/tmp/ds41-fp8/reports/<папка замера>/long-context.json
```

Отчёт скопировать в комплект: `reports/<дата>/` — профиль, команду, versions, smoke, bench.json, SpecDecoding. Адреса аренды, токены и hostname в комплект не класть.

**Клиент.** API слушает только loopback сервера. С ноутбука — `ops/tunnel.sh`, а если шлюз не пропускает `ssh -L` (Cloud.ru Jupyter) — `ops/ssh-exec-tunnel.py` + `ops/tcpbridge.py`. free-code — `ops/configure-free-code.py --context 1048576` для 8-GPU профиля. Подробности — [docs/10](../../docs/10-clients-and-operations.md).

**6. Остановка.** `kill <pid>` из вывода `serve.sh` (или PID слушателя порта из `ss -ltnp`). Дождаться, пока `VLLM::Worker*` завершатся и память на картах станет 0. Чужие процессы не трогать.

## Откат, если быстрый профиль не стартует

По одному перезапуску, каждый — отдельный отчёт:

1. Убрать `--speculative-config`, `GPU_MEMORY=0.95`: около 109 ток/с.
2. Ещё и `EAGER=1`: около 11,5 ток/с, но это самый простой путь для диагностики.

Если не стартует и eager — искать причину в логе и в [каталоге ошибок](../../docs/09-lessons-and-errors.md), не менять версии на `latest`.

## Ловушки

- **Разброс.** Повтор на другом узле того же типа дал 199/641 против 206/644. Расхождение в несколько процентов — норма; больше 10% — искать причину (чужая нагрузка, другие версии, другой профиль).
- **Не оставлять GPU пустыми.** 4-GPU профиль на 8-GPU узле работает, но половина карт простаивает, KV-кэш в 28 раз меньше (0,64 против 17,7 млн токенов), окно ограничено 65536, и одновременных запросов помещается меньше.
- **Окно на 4 GPU.** С DSpark KV хватает только на 639 692 токена, поэтому там окно 65536. На 8 GPU — полное 1048576. Длинный промпт — это минуты prefill: 1M токенов около 4 минут. Ограничивать карты только по прямой просьбе владельца узла.
- **Длина черновика DSpark.** Приёмка по позициям 0,69 / 0,44 / 0,25; в checkpoint 3 MTP-слоя, у автора kit k=5 медленнее k=3. k=4 не проверялся, ожидаемый выигрыш не больше ~5%.
- **Первый запрос медленный** — JIT. Не показывать и не мерить его.
- **Обрывы SSH** убивают процессы, запущенные без `setsid nohup`.
- **Остатки прошлого старта.** Упавший запуск может оставить `api_server` и часть `VLLM::Worker*`; `serve.sh` откажется стартовать, пока они держат память.
- **`pkill -f ШАБЛОН` в zsh-сессии** совпадает с командой самой SSH-сессии. Останавливать по PID.
