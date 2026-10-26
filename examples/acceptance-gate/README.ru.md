# Пример внешней приёмки

[English](README.md)

Выбранный владельцем проверяющий выполняет восемь реальных проверок JSON CLI:
целочисленная сумма, большие числа и неверные входные данные. Приложение и
проверяющий запускаются в официальном Windows sandbox Codex, без модели и входа
в подписку.

Из корня репозитория сначала посмотрите контракт без исполнения:

```powershell
python codex-flow.py --repo examples/acceptance-gate verify --acceptance-file examples/acceptance-gate/contract.json
```

Выполните проверки с установленным официальным Codex CLI:

```powershell
python codex-flow.py --repo examples/acceptance-gate --codex <абсолютный-путь-к-codex> verify --acceptance-file examples/acceptance-gate/contract.json --execute
```

Код выхода 0 и `accepted: true` требуют прохождения всех восьми проверок,
неизменных хешей исходников и проверяющего, полного захвата результата sandbox.
Пустой, отсутствующий или старый отчёт, ошибка, тайм-аут и изменение исходников
блокируют приёмку. Подробные квитанции сохраняются в игнорируемом каталоге
`.codex-flow/runs/` этого примера.

[Полный контракт и ограничения](../../docs/acceptance-gate.ru.md). Это пример
механизма приёмки, без нового модельного бенчмарка и гарантии полного качества кода.
