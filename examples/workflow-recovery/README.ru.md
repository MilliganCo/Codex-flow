# Принятая фикстура и воспроизводимая проверка восстановления

[English](README.md)

Файл accepted/sum_cli.py побайтно совпадает с фикстурой, принятой реальным sandbox
в [контролях восстановления](../../benchmarks/workflow-recovery-20261027/README.ru.md).
Его создал явно помеченный фиктивный генератор; Sol и Luna здесь не генерировали код.

Посмотреть проверки владельца без исполнения:

```powershell
python codex-flow.py --repo examples/workflow-recovery/accepted verify --acceptance-file examples/workflow-recovery/acceptance.json
```

Чтобы выполнить восемь проверок в официальном Windows sandbox, перед `verify`
добавьте глобальный `--codex <абсолютный-путь-к-codex>`, а после контракта —
`--execute`. Модель и вход в подписку для проверки не требуются.

Для полного контроля аварии процесса и resume без модели используйте
`tools/check_workflow_recovery.py` с новым коротким `--output` и установленным
`--codex`. См. [команды workflow](../../docs/workflows.ru.md). Обычная генерация
workflow использует настоящий native backend и требует явного включения.
