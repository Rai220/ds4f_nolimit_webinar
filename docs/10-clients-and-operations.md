# Клиенты, API, UI и обслуживание

Обновлено 2026-09-24. Здесь параметры подключения. Конкретный SSH-адрес берётся из панели аренды; в [отчёте стенда](07-vast-exl3.md) его нет. Секретов в примерах нет.

## Различать адреса

| Уровень | Пример текущего стенда | Назначение |
|---|---|---|
| Runtime на сервере | `127.0.0.1:18080` | vLLM, оба API |
| OpenAI API через локальный tunnel | `http://127.0.0.1:18081/v1` | models, chat/completions |
| Anthropic API через тот же tunnel | `http://127.0.0.1:18081` | клиент добавляет `/v1/messages` сам |
| Model UI backend | `127.0.0.1:17860` | HTML/JS и proxy `/api/*` |
| Vast Caddy UI | container 7860 → mapped port из панели | штатная auth перед UI |
| UI proxy API | внешний адрес панели + `/api` | `/api/models`, `/api/chat/completions`, с auth Vast |

На этом стенде **отдельный публичный стандартный `/v1` endpoint напрямую не публиковался**. OpenAI-совместимые запросы возможны через UI proxy `/api`, а штатный `/v1` доступен по SSH. Наличие старого mapped порта шаблонного SGLang не означает, что новая модель слушает за ним.

Для следующего публичного API использовать существующий gateway/proxy с авторизацией и проверить forwarding, paths, streaming, timeouts. Не менять bind на `0.0.0.0` без понимания auth и карты портов. В Docker `0.0.0.0` внутри контейнера допустим при host publish на loopback; в уже готовом Vast-контейнере это другой контур.

## SSH-туннель

Заранее проверить ключ хоста по доверенному каналу и убедиться, что он есть в known_hosts. Скрипт намеренно использует StrictHostKeyChecking=yes; неизвестный ключ не обходить через `no`.

```bash
export SSH_TARGET=user@host
export SSH_PORT=22
export LOCAL_PORT=18081
export REMOTE_PORT=18080
export SSH_KEY="$HOME/.ssh/id_ed25519"
bash ops/tunnel.sh
```

Туннель работает в foreground; отдельный терминал можно закрыть после работы. ExitOnForwardFailure выявляет конфликт local port. Для постоянной работы запускать эту же команду через менеджер пользователя: launchd на macOS, systemd --user на Linux. Настройки окружения передавать этому менеджеру явно — он не наследует интерактивный shell profile.

Постоянный туннель на local port 18081 запускать отдельным заданием пользователя. Не перепутать localhost сервера и ноутбука и не перехватывать чужой занятый порт. Туннель другого сервера в это задание не подмешивать.

При прямом SSH после proxy можно использовать HostKeyAlias лишь после подтверждения, что это тот же сервер и тот же host key. Поле `SSH_HOST_KEY_ALIAS` у `ops/tunnel.sh` необязательно; старое имя/порт не копировать на новую аренду.

### Шлюз, который не пропускает `ssh -L` (ноутбуки Cloud.ru Jupyter)

Шлюз отвечает на проброс порта сам: `target host connection failed`. SSH-команда при этом работает, поэтому мост из двух частей: [ops/tcpbridge.py](../ops/tcpbridge.py) лежит на сервере и соединяет stdin/stdout с локальным портом runtime, а [ops/ssh-exec-tunnel.py](../ops/ssh-exec-tunnel.py) слушает loopback на ноутбуке и на каждое соединение запускает `ssh … python3 -u tcpbridge.py PORT`. Host key проверяется строго, как в `tunnel.sh`.

```bash
python3 ops/ssh-exec-tunnel.py --local-port 18083 --ssh-target USER@HOST --ssh-port 2222 \
  --ssh-key "$HOME/.ssh/id_ed25519" --remote-bridge /ПУТЬ/КОМПЛЕКТА/ops/tcpbridge.py --remote-port 18080
```

Каждое новое соединение стоит одного SSH-рукопожатия (около 1,6 с на Cloud.ru), дальше HTTP keep-alive его переиспользует. Постоянный запуск — LaunchAgent с `KeepAlive` на macOS или `systemd --user`; скрипт положить вне каталога, который может переехать. Проверено 2026-09-24: `/v1/models`, smoke с tools, Anthropic `/v1/messages` и free-code Read через мост.

## Проверка API

```bash
python3 ops/smoke.py --base-url http://127.0.0.1:18081/v1 \
  --model deepseek-v4.1-flash --no-thinking --tools
```

Для защищённого gateway — `--token-env MODEL_API_TOKEN`, где значение уже безопасно загружено в env. Не писать token в URL, команды или JSON profile. В UI proxy указывать base URL с `/api`, в обычном OpenAI API — с `/v1`.

Проверять не только HTTP 200: правильный model ID, завершение по `stop`, раздельные content/reasoning, SSE `[DONE]`, формат tool calls и повторный ответ после результата инструмента. Reasoning может быть в `reasoning` или `reasoning_content`; поддержка зависит от версии parser/API.

Клиент исполняет инструмент, модель только предлагает вызов. Для приёмки сначала фиксированное безопасное чтение, затем учебный проект. Не давать тестовому агенту доступ ко всему home/vault для проверки «работает ли».

## Подключение free-code без изменения исходников

Полный повторяемый путь описан в скиле [skills/free-code-deepseek](../skills/free-code-deepseek/SKILL.md): сборка на закреплённом commit, туннель как служба пользователя, профиль, команда `free-code` через symlink без alias, проверка настоящим клиентом и работа со встроенным `free-code --yolo`. Ниже — детали самого профиля.

Проверенные сборки: `2.1.251-free-code.1` (commit `a89531f`, 2026-09-25, есть встроенный `--yolo`) и более ранняя 2.1.119 (2026-09-22, без `--yolo`). Репозиторий — [gitverse.ru/krestnikov/free_code](https://gitverse.ru/krestnikov/free_code) (для git: `https://gitverse.ru/krestnikov/free_code.git`), в этом окружении checkout лежит в `../free_code` (имя каталога с подчёркиванием). `install.sh` оттуда не запускать: он перезаписывает `~/.local/bin/free-code` и правит `~/.claude/settings.json`. Перед настройкой новой сборки читать её README/CLAUDE и проверить native Anthropic API. В этой сборке `CLAUDE_CODE_USE_OPENAI=1` означает Codex OAuth, а не произвольный OpenAI base URL.

Создать новый изолированный профиль и launcher:

```bash
python3 ops/configure-free-code.py \
  --binary /ABS/free_code/cli \
  --profile "$HOME/.config/free-code/my-model" \
  --launcher "$HOME/.local/bin/free-code-my-model" \
  --api-base http://127.0.0.1:18081 \
  --model deepseek-v4.1-flash --context 65536 --output-tokens 8192 --effort high
```

`--context` ставить равным окну сервера. При 1048576 скрипт не задаёт `CLAUDE_CODE_DISABLE_1M_CONTEXT`: с этим флагом клиент сам ограничивает себя меньшим окном. Для меньших окон флаг остаётся.

Скрипт рассчитан на **loopback + SSH**, не на неаутентифицированный внешний API. Несекретная API-заглушка нужна SDK, доступ обеспечивает SSH. Он не перезаписывает существующие settings/launcher и не меняет основной `free-code` автоматически. Для существующего профиля сначала прочитать настройки; менять адреса и лимиты согласованно.

Профиль задаёт все model aliases, отдельный CLAUDE_CONFIG_DIR, отключает ненужные beta headers/tool search и API-логи/S3. OAuth/Bedrock/Vertex/Foundry маршруты очищаются в launcher. Effort `high` выбран потому, что V4.1 отвергает `medium`; для другой модели проверить допустимые значения. Output budget всегда меньше context, а место требуется ещё и system/tools/history.

Проверка реальной сборкой:

```bash
mkdir -p /tmp/free-code-model-check
printf 'WEBINAR-CHECK-73921\n' > /tmp/free-code-model-check/check.txt
cd /tmp/free-code-model-check
"$HOME/.local/bin/free-code-my-model" -p \
  'Read check.txt with the Read tool and return its contents.' \
  --tools Read --allowedTools Read --no-session-persistence \
  --setting-sources user --output-format stream-json --verbose > result.jsonl
```

В результате должен быть настоящий `tool_use` Read и правильный финальный ответ, `is_error=false`, пустые permission denials. Нулевой exit code или `subtype=success` без `is_error` проверять недостаточно: наблюдался JSON с subtype success, но is_error true и HTTP400.

Эта проверка, а также Bash под `--yolo` и отказ без него, собраны в `skills/free-code-deepseek/scripts/verify.py`.

Проверка compiled free-code на стенде заняла 2 turns. Прямой запуск бинарника без launcher не обязан наследовать профиль. Исходники и бинарник не менялись. Продолжение старой сессии от другой модели может принести несовместимую историю — первую проверку делать новой сессией.

## Подключение встроенного Vast Model UI

Сначала прочитать `/opt/model-ui/README.md`, app.py, launcher и нужные части JS/HTML. В исследованном образе launcher загружает `/etc/environment` и workspace env, а приложение ждёт `/v1/models` и строит HTML один раз при старте.

```bash
python3 ops/configure-model-ui.py \
  --api-base http://127.0.0.1:18080 --model deepseek-v4.1-flash --max-output 4096
# После просмотра перечисленных файлов применить тот же вызов с --apply.
python3 ops/configure-model-ui.py \
  --api-base http://127.0.0.1:18080 --model deepseek-v4.1-flash --max-output 4096 --apply
supervisorctl restart model-ui
```

Скрипт проверяет известные anchors, задаёт backend после чтения окружения и до проверки MODEL_NAME, включает Chat, адаптирует renderer к обоим reasoning fields и slider. Пути `--app-dir`/`--launcher` можно изменить; при иной структуре образа нужно изучить её, а не отключать проверки. Сохранённый `deploy/configure-model-ui.py` — исторический вариант для старого образа; новый — `ops/`.

Порт UI, Caddy и авторизация не меняются. Открыть прежнее **Model UI → Launch Application** или Secure Tunnel Link, обновить браузер. Внешний URL без token может вернуть 401; это не сбой модели. Само изменение env не обновляет уже запущенный HTML/JS — нужен restart UI. Модель при этом перезапускать не требуется.

Приёмка: HTML содержит новый model ID, фактически выдаваемый JS поддерживает reasoning, `/api/models` правильный, streaming через `/api/chat/completions` завершается, а внешний Caddy/Quick Tunnel пропускает авторизованный запрос. Текущая проверка была на HTTP/API уровне, визуального теста браузером не выполняли.

## Обслуживание и завершение аренды

Сохранить service config/profile и версии вне арендуемой файловой системы. Для Supervisor: reread → update конкретной программы → status/logs → реальный API smoke. `update` изменённой программы может её перезапустить и оборвать запросы. В контейнере не запускать `systemctl`, если init отсутствует.

Использовать отдельные каталоги caches для версии/toolkit/arch. XDG_CACHE_HOME не гарантирует переноса всех caches: для SGLang отдельно SGLANG_CACHE_DIR/TILELANG_CACHE_DIR/FLASHINFER_WORKSPACE_BASE; для vLLM VLLM_CACHE_ROOT/TORCH_EXTENSIONS_DIR. На H200 часть FlashInfer cache всё равно оказалась в `/root/.cache/flashinfer`; проверить фактические файлы перед оценкой свободного места.

После изменения runtime/TP/контекста повторить короткую приёмку. После переноса на новую GPU пересобрать/проверить kernels. При рестарте сохранить веса/cache, не скачивать их повторно без причины.

Перед уничтожением узла вынести нужные инструкции, profiles, manifests и обезличенные результаты. Проверить, нужен ли перенос весов на отдельный том. Остановка модели не завершает аренду; цена, баланс и завершение аренды — отдельное действие владельца. Не удалять том или арендный узел без поручения.
