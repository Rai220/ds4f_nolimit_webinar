---
name: free-code-deepseek
description: Собрать free-code из исходников, установить, подключить к DeepSeek V4.1 Flash (или другой модели) на арендованном сервере через SSH, сделать команду `free-code` и работать с встроенным флагом `--yolo`. Использовать, когда просят «установи/собери free-code», «подключи free-code к дипсику / к новому серверу», «настрой alias / команду free-code», «запусти free-code с --yolo», «free-code не отвечает». Не для запуска самой модели на сервере: это skills/ds4-fp8-vllm.
---

# free-code → DeepSeek: сборка, подключение, `--yolo`

Самодостаточный рецепт для агента, который склонировал этот комплект, и для человека. Команды даны от корня комплекта. Общие правила — [AGENTS.md](../../AGENTS.md), подробности клиента — [docs/10](../../docs/10-clients-and-operations.md).

Результат: на ноутбуке есть команда `free-code`. Она ходит в модель на сервере по SSH и принимает любые флаги, включая `free-code --yolo`. Shell alias не нужен: `--yolo` встроен в свежие сборки free-code, а команда — это symlink на launcher.

Скрипты скила:

- [scripts/tunnel-agent.py](scripts/tunnel-agent.py) — пишет LaunchAgent (macOS) или unit systemd `--user` (Linux), который держит туннель к API сервера;
- [scripts/verify.py](scripts/verify.py) — сквозная проверка настоящим клиентом: API, флаг `--yolo`, Read, Bash под `--yolo`, отказ без `--yolo`.

Исходники free-code: [gitverse.ru/krestnikov/free_code](https://gitverse.ru/krestnikov/free_code), для git — `https://gitverse.ru/krestnikov/free_code.git` (анонимный HTTPS, токен не нужен).

Из общего `ops/` используются `configure-free-code.py` (профиль и launcher), `tunnel.sh`, `ssh-exec-tunnel.py` и `tcpbridge.py` (туннель).

## Что проверено

| Дата | Клиент | Сервер | Результат |
|---|---|---|---|
| 2026-09-25 | macOS 26.6 arm64, free-code `a89531f` = `2.1.251-free-code.1`, bun 1.3.11 | Cloud.ru 8×H100, FP8 на vLLM 0.30.0, окно 1048576; exec-мост на `127.0.0.1:18083` | `verify.py --negative`: 5 из 5 PASS за 12,7 с. Read — 2 turns; `--yolo` + Bash — режим `bypassPermissions`, файл создан, 2 turns; без `--yolo` запись отклонена (denials: Bash) |
| 2026-09-25 | тот же Mac, пустой каталог | тот же | Шаги 1, 3 и 5 с нуля: неглубокий fetch `a89531f` (4,7 с), `bun install` и `bun run build` (8,7 с при прогретом кэше bun), `cli` 187 МБ; новый профиль с окном 1048576 и ответом до 16384 — `verify.py --negative` 5 из 5 PASS |
| 2026-09-26 | тот же бинарник, без пересборки | другой ноутбук Cloud.ru 8×H100, тот же FP8 и окно 1048576 | Новый `NAME`, новая служба exec-туннеля на свободном локальном порту, прежний туннель не трогали. `verify.py --negative`: 5 из 5 PASS за 31 с |
| 2026-09-22 | free-code 2.1.119 | Vast 2×H200, EXL3, `ssh -L` на 18081 | Read round trip. В этой версии `--yolo` ещё нет |

**Не проверено:** клиент на Linux; unit systemd на живой машине. Служба LaunchAgent, записанная `tunnel-agent.py`, загружена с нуля 2026-09-26 и прошла `verify.py`. Шаг 4 (symlink) выполнен вручную 2026-09-24 и снова 2026-09-26: прежний `free-code` переименован, новый указывает на launcher нового узла. Холодный `bun install` без кэша не замерялся. `install.sh` из репозитория free-code намеренно не используется (см. шаг 1). Сессии free-code (`*.jsonl`) в комплект не класть.

Отчёты — [reports/2026-09-25/free-code](../../reports/2026-09-25/free-code/).

## Параметры

Всё ниже — параметры, не константы. Значения текущего стенда даны для примера.

| Параметр | Пример | Откуда взять |
|---|---|---|
| `FC_SRC` | `$HOME/free-code` | Каталог исходников free-code. Уже существующий checkout не клонировать заново |
| `FC_REV` | `a89531fa5e0f03a15f0e579e47b381da443d3577` | Полный SHA. Это минимальный commit со встроенным `--yolo`; более новый брать только с проверкой шага 5 |
| `NAME` | `deepseek-8xh100` | Короткое имя подключения: профиль, launcher и служба туннеля |
| `SSH_TARGET`, `SSH_PORT`, `SSH_KEY` | `user@host`, `2222`, `~/.ssh/id_ed25519` | Панель аренды или владелец. Ключ хоста — только из доверенного канала |
| `REMOTE_PORT` | `18080` | Порт API на loopback сервера (`PORT` в профиле сервера) |
| `LOCAL_PORT` | `18083` | Свободный loopback-порт ноутбука. Не занимать порт чужого туннеля |
| `MODEL` | `deepseek-v4.1-flash` | Поле `id` из `/v1/models` |
| `CONTEXT` | `1048576` | Поле `max_model_len` из `/v1/models`, **равно окну сервера** |
| `OUTPUT` | `16384` при 1M, `8192` при 65536 | Меньше `CONTEXT`; служебный промпт free-code около 28 тыс. токенов |

## 0. Посмотреть, что уже есть (только чтение)

```bash
command -v free-code; ls -la ~/.local/bin/ | grep free-code
ls ~/.config/free-code/ 2>/dev/null
launchctl list | grep -i tunnel            # Linux: systemctl --user list-units | grep -i tunnel
lsof -nP -iTCP:$LOCAL_PORT -sTCP:LISTEN    # порт свободен или уже наш туннель
command -v bun && bun --version
```

Если `free-code` уже ведёт в launcher другой модели, этот launcher и его профиль не трогать. Новому подключению дать новое `NAME`. Существующие профили, launcher и службы не перезаписывать: `configure-free-code.py` и `tunnel-agent.py` сами откажутся это делать.

## 1. Собрать free-code

`install.sh` из репозитория free-code для этого рецепта **не запускать**. У него три побочных эффекта:

1. Он берёт незакреплённый `master` в `~/free-code`.
2. Он перезаписывает `~/.local/bin/free-code` через `ln -sf`.
3. Он выполняет `configure-defaults.ts`, и тот правит `~/.claude/settings.json` (модель Fable, effort xhigh). Это общий конфиг Claude Code на ноутбуке.

Собирать вручную:

```bash
command -v bun || curl -fsSL https://bun.sh/install | bash   # нужен bun >= 1.3.11
export PATH="$HOME/.bun/bin:$PATH"
FC_REV=a89531fa5e0f03a15f0e579e47b381da443d3577               # полный SHA: fetch по SHA короткий не примет
if [ ! -e "$FC_SRC" ]; then            # новый каталог: только нужный commit, без истории
  git init -q "$FC_SRC" && git -C "$FC_SRC" remote add origin https://gitverse.ru/krestnikov/free_code.git
  git -C "$FC_SRC" fetch --depth 1 origin "$FC_REV"
fi
git -C "$FC_SRC" status --short        # должно быть пусто; иначе см. ниже
# Существующий полный checkout не делать shallow: докачать обычным fetch, если commit ещё нет.
git -C "$FC_SRC" cat-file -e "$FC_REV^{commit}" 2>/dev/null || git -C "$FC_SRC" fetch origin
git -C "$FC_SRC" checkout --detach "$FC_REV"
cd "$FC_SRC" && bun install --frozen-lockfile && bun run build
./cli --version                       # 2.1.251-free-code.1 (Claude Code) или новее
./cli --help | grep -- '--yolo'       # --yolo, --dangerously-skip-permissions
```

Забирать только нужный commit, без истории. Полный `git clone` этого репозитория 2026-09-25 не продвинулся за 5 минут: в истории раньше лежал бинарник. Неглубокий fetch занял 4,7 с и 14 МБ. Репозиторий открыт для анонимного HTTPS, токен не нужен.

Если `$FC_SRC` существует, но это не git, или `git status --short` в нём не пустой, это чужая работа. Commit не переключать, выбрать другой `FC_SRC`. Бинарник `$FC_SRC/cli` общий для всех launcher, которые на него указывают. Пересборка обновляет их все, а уже открытые сессии продолжают работать на старом файле до перезапуска.

## 2. Туннель к API сервера

API сервера слушает только loopback. С ноутбука к нему ведёт SSH. Открытый в интернет API без авторизации не делать.

1. Ключ хоста получить по доверенному каналу и добавить в `~/.ssh/known_hosts`. Скрипты используют `StrictHostKeyChecking=yes`, неизвестный ключ не обходить.
2. Узнать модель и окно на сервере:
   ```bash
   ssh -p $SSH_PORT $SSH_TARGET 'curl -s 127.0.0.1:'$REMOTE_PORT'/v1/models'
   ```
   Из ответа взять `id` → `MODEL` и `max_model_len` → `CONTEXT`.
3. Выбрать режим. Сначала попробовать `ssh -L` в foreground: `SSH_TARGET=… SSH_PORT=… LOCAL_PORT=… REMOTE_PORT=… bash ops/tunnel.sh`, затем в другом терминале `curl 127.0.0.1:$LOCAL_PORT/v1/models`.
   - Пришёл JSON — режим **forward** (Vast и обычные SSH-серверы). Остановить foreground-туннель.
   - Пришло `target host connection failed` — шлюз не пропускает проброс (Cloud.ru Jupyter). Режим **exec**.
4. Для **exec** на сервере нужен `ops/tcpbridge.py`. Если комплекта на сервере нет, положить один файл:
   ```bash
   ssh -p $SSH_PORT $SSH_TARGET 'mkdir -p /var/tmp/free-code-bridge && cat > /var/tmp/free-code-bridge/tcpbridge.py' < ops/tcpbridge.py
   ```
   Каталог — параметр. Годится любой постоянный путь пользователя вне общего NFS-кэша.
5. Скопировать скрипт туннеля в постоянное место вне checkout, который может переехать, и сгенерировать службу:
   ```bash
   mkdir -p ~/.config/free-code/tunnels
   install -m 755 ops/ssh-exec-tunnel.py ~/.config/free-code/tunnels/$NAME-ssh-exec-tunnel.py   # exec
   # forward: install -m 755 ops/tunnel.sh ~/.config/free-code/tunnels/$NAME-tunnel.sh
   python3 skills/free-code-deepseek/scripts/tunnel-agent.py --mode exec --label local.$NAME-tunnel \
     --tunnel-script ~/.config/free-code/tunnels/$NAME-ssh-exec-tunnel.py \
     --local-port $LOCAL_PORT --ssh-target $SSH_TARGET --ssh-port $SSH_PORT --ssh-key $SSH_KEY \
     --remote-bridge /var/tmp/free-code-bridge/tcpbridge.py --remote-port $REMOTE_PORT
   ```
   Сначала можно добавить `--print` и посмотреть файл. Скрипт печатает команды загрузки, состояния, выгрузки и путь к логам. Выполнить загрузку (`launchctl bootstrap …` или `systemctl --user enable --now …`).
6. Проверить: `curl -s 127.0.0.1:$LOCAL_PORT/v1/models`. Через exec-мост каждое новое соединение стоит одного SSH-рукопожатия (около 1,6 с на Cloud.ru), дальше keep-alive.

## 3. Профиль и launcher

```bash
python3 ops/configure-free-code.py \
  --binary "$FC_SRC/cli" \
  --profile "$HOME/.config/free-code/$NAME" \
  --launcher "$HOME/.local/bin/free-code-$NAME" \
  --api-base http://127.0.0.1:$LOCAL_PORT \
  --model "$MODEL" --context $CONTEXT --output-tokens $OUTPUT --effort high
```

Launcher задаёт отдельный `CLAUDE_CONFIG_DIR`, адрес API без `/v1` и все model aliases на `MODEL`. Он отключает логи и выгрузку в S3, выключает OAuth, Bedrock и Vertex. В конце он вызывает `exec cli "$@"`, поэтому любые флаги, включая `--yolo`, проходят как есть. `--effort high` нужен для DeepSeek V4.1: сервер отвергает `medium`. Для другой модели допустимые значения проверить отдельно.

## 4. Команда `free-code` без alias

Команда `free-code` — это symlink в `~/.local/bin` на launcher. Shell alias не нужен: symlink работает в любой оболочке, в скриптах, в `-p`-режиме и у других агентов.

```bash
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo 'добавить: export PATH="$HOME/.local/bin:$PATH" в ~/.zshrc или ~/.bashrc';; esac
L=~/.local/bin/free-code
if [ -e "$L" ] || [ -L "$L" ]; then mv "$L" "$L.before-$NAME-$(date +%Y%m%d)"; fi   # прежний вариант сохраняется
ln -s "$HOME/.local/bin/free-code-$NAME" "$L"
hash -r 2>/dev/null; rehash 2>/dev/null; readlink ~/.local/bin/free-code
```

Шаг необязателен. Если владелец хочет оставить прежний `free-code`, новое подключение запускается как `free-code-$NAME`.

## 5. Проверка настоящим клиентом

HTTP 200 и `/v1/models` не доказывают, что клиент работает. Нужна законченная сессия с инструментом:

```bash
python3 skills/free-code-deepseek/scripts/verify.py --launcher ~/.local/bin/free-code \
  --model "$MODEL" --base-url http://127.0.0.1:$LOCAL_PORT --negative --json /tmp/free-code-verify.json
```

Ожидается `ALL PASS`, всего 5 проверок:

1. `/v1/models` отдаёт `MODEL`.
2. `--yolo` виден в `--help`.
3. Read в обычном режиме: `is_error=false`, нет permission denials, в ответе контрольная строка.
4. Под `--yolo` Bash создаёт файл: режим `bypassPermissions`, denials пустые.
5. Без `--yolo` тот же Bash отклонён: файла нет, в denials есть Bash.

Каждый прогон — новая сессия в новом каталоге, auto-memory отключена. Логи `*.jsonl` и `*.stderr` остаются в рабочем каталоге.

Проверять `is_error`, а не только exit code: наблюдался ответ с `subtype=success`, но `is_error=true` и HTTP 400. Пятый прогон ограничен `--max-turns 3`. Без ограничения модель после отказа 60 ходов подряд искала обходные способы записи.

## 6. Работа с `--yolo`

```bash
cd ~/projects/demo            # каталог проекта, не $HOME
free-code --yolo              # интерактивно
free-code --yolo -p 'задание' < /dev/null      # без TUI
free-code --yolo --resume     # продолжить сессию
```

- `--yolo` — штатный синоним `--dangerously-skip-permissions`. Он есть с commit `a89531f` (`2.1.251-free-code.1`) и виден в `free-code --help`. Команда `free-code ssh <host> --yolo` его тоже понимает. В старой сборке (например 2.1.119) флага нет: пересобрать по шагу 1, а не заводить alias.
- В интерактивном режиме при первом запуске с `--yolo` TUI один раз спрашивает подтверждение. Отвечает человек. Ответ сохраняется в `settings.json` профиля (`skipDangerousModePermissionPrompt`). Агент не должен заранее записывать это поле за владельца.
- Для `-p` добавлять `< /dev/null`, иначе клиент 3 секунды ждёт stdin и пишет предупреждение.
- От root флаг запрещён, пока не задан `IS_SANDBOX=1`. Задавать его только в настоящем изолированном контейнере, не на ноутбуке.
- `--yolo` выполняет без вопросов любые команды модели: удаление, сеть, запись вне проекта. Запускать в каталоге проекта или в учебном каталоге ([examples/demo-project](../../examples/demo-project/README.md)), не в `$HOME` и не рядом с ключами. `permissions.defaultMode: bypassPermissions` в настройках профиля не ставить: режим должен включаться явно, флагом.

## Смена сервера или окна

- **Новый адрес сервера, тот же локальный порт.** Выгрузить службу туннеля (`launchctl bootout gui/$(id -u)/local.$NAME-tunnel`), удалить её plist или unit и сгенерировать заново по шагу 2. Профиль не меняется.
- **Другое окно или модель.** Проще создать новый профиль с новым `NAME` (шаги 3–4). При правке на месте менять `CLAUDE_CODE_MAX_CONTEXT_TOKENS` согласованно в launcher и в `settings.json`. `CLAUDE_CODE_DISABLE_1M_CONTEXT` должен быть только при окне меньше 1048576.
- Уже открытые сессии free-code новый лимит не подхватывают. Их нужно перезапустить; старую сессию от другой модели не продолжать.

## Откат

```bash
ln -sfn "$(readlink ~/.local/bin/free-code.before-$NAME-YYYYMMDD)" ~/.local/bin/free-code   # или mv файла назад
launchctl bootout gui/$(id -u)/local.$NAME-tunnel   # Linux: systemctl --user disable --now local.$NAME-tunnel.service
```

Профиль, launcher и файл службы удалять только по просьбе владельца.

## Неполадки

| Симптом | Причина | Что делать |
|---|---|---|
| `curl 127.0.0.1:$LOCAL_PORT` — `connection refused` | Служба туннеля не загружена или упала | `launchctl print gui/$(id -u)/local.$NAME-tunnel`, лог `tunnel-error.log`. Затем на сервере `ss -ltnp \| grep $REMOTE_PORT` |
| `target host connection failed` | Шлюз не пропускает `ssh -L` | Режим exec (шаг 2) |
| `Host key verification failed` | Ключа нет в known_hosts или он сменился | Сверить по доверенному каналу; `StrictHostKeyChecking=no` не ставить |
| `error: unknown option '--yolo'` | Старая сборка | Шаг 1 с `FC_REV` не ниже `a89531f` |
| `--dangerously-skip-permissions cannot be used with root/sudo` | Клиент запущен от root | Запускать от пользователя; `IS_SANDBOX=1` только в изолированном контейнере |
| HTTP 400 про `reasoning_effort` | `medium` не принимается DeepSeek V4.1 | `--effort high` |
| Клиент быстро упирается в контекст | Окно клиента больше или меньше серверного | `CONTEXT` = `max_model_len`, при 1M без `CLAUDE_CODE_DISABLE_1M_CONTEXT` |
| Модель не та или просит логин | Бинарник запущен напрямую, без launcher | Запускать `free-code`, то есть symlink на launcher; `readlink ~/.local/bin/free-code` |
| После пересборки free-code изменился `~/.claude/settings.json` | Запускался `install.sh` | Вернуть из `settings.json.bak-*` рядом; дальше собирать по шагу 1 |
