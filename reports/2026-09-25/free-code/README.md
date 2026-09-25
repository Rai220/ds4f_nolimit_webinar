# free-code → DeepSeek, 2026-09-25

Клиент: macOS 26.6 arm64, bun 1.3.11, free-code `a89531fa5e0f03a15f0e579e47b381da443d3577` = `2.1.251-free-code.1`.
Сервер: Cloud.ru 8×H100, dealignai DeepSeek V4.1 Flash UNCENSORED FP8, vLLM 0.30.0, окно 1048576, exec-мост на ноутбуке `127.0.0.1:18083`.

- `verify-existing-launcher.json` — рабочая команда `free-code` (symlink → launcher профиля 8×H100), `verify.py --negative`: 5/5 PASS, 12,7 с.
- `build.txt` — неглубокий fetch закреплённого commit в пустой каталог, `bun install --frozen-lockfile`, `bun run build` (8,7 с, кэш bun прогрет), SHA256 бинарника.
- `verify-fresh-build.json` — новый профиль `ops/configure-free-code.py --context 1048576 --output-tokens 16384 --effort high` на свежем бинарнике: 5/5 PASS.

Полный `git clone` того же репозитория не продвинулся за 5 минут и был остановлен.
Отрицательная проверка без `--max-turns` (отдельный ручной прогон) длилась 303 с: 60 ходов, 48 отказов (Bash, Write, Read, Glob), файл не создан.
