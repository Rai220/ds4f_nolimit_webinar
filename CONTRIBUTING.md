# Изменение комплекта

Прочитайте AGENTS.md и README.md. Изменяйте профиль конкретного маршрута; не объявляйте другой GPU или формат весов проверенным по результатам старого стенда.

Локальные проверки из корня:

```bash
python3 -m unittest discover -s tests -v
for script in ops/*.sh deploy/*.sh scripts/*.sh; do bash -n "$script" || exit; done
bash ops/run-model.sh profiles/exl3-h200.env.example --dry-run
bash ops/run-model.sh profiles/fp8-sglang.env.example --dry-run
```

В examples/demo-project намеренно падающие тесты — это задание модели, отдельно от проверок комплекта.

При изменении installer/patches нужна чистая GPU-установка и приёмка из docs/11-live-cold-start.md. Сохраните версии, профиль без секретов и результаты в reports/. Локальный unit test не заменяет GPU-проверку.

Не добавляйте веса, токены, частные адреса, локальные настройки и кэши. Проверяйте состав архива отдельно от .gitignore. Перед распространением выберите лицензию авторских материалов и проверьте условия моделей и upstream-компонентов; готовая модель и сторонние исходники в комплект не включены.
