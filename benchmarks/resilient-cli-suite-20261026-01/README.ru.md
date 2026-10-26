# Resilient CLI: основной критерий не выполнен

[English](README.md) · [Сводка](evidence/cohort/series-result.json) · [Происхождение метаданных](metadata-publication.json)

**Ledger завершён с оценкой 100/100 в обеих ветках. SafeZip B завершился ошибкой
HTTP 429 на первом запросе; ускорение без потери качества не доказано.**
Обе задачи остаются в знаменателе; неудачная ветка не считается быстрой.

| Задача | A: секунды / статус | B: секунды / статус | Попытки / завершённые A; B | Оценка A/B |
|---|---|---|---|---:|
| LedgerReconcile | 647,438 / завершён | 631,282 / завершён | 14/14; 14/14 | 100 / 100 |
| SafeZip | 997,438 / завершён | 37,391 / ошибка HTTP 429 | 12/12; 1/0 | 100 / 40, отклонён |

Разница Ledger — 16,156 с, около 2,5% времени Solo; порог `A/B >= 1.10` не
выполнен. Для SafeZip допустимого отношения времени нет. Всего 41 физическая
попытка, 40 завершённых. Частичные баллы за обработку неверных входов не означают
работающий CLI у B. Независимые SDK-оценки и печати сохраняют отрицательный
результат и неизменность исходников и checker.

В [frozen-runtime](frozen-runtime/) сохранены точные 16 файлов commit
`4f794d7c9dabaecc1a1332295babf6e63c555cd0`. Отдельная [реальная проверка](evidence/prerequisites/resilient-prerequisite-20261026-01/prerequisite-result.json)
прошла 23 проверки с девятью native-запросами; [синтетическое восстановление](evidence/proofs/native-http-recovery-proof-20261026-04/proof-result.json)
прошло пять случаев. Они не получают зачёт в бенчмарке и не исправляют его провал.
[Последняя серия](../efficient-cli-suite-20261026-02/README.ru.md) завершила обе
задачи, но Flow остался медленнее.

## CLI-демо

Принятые решения A содержат исходные примеры и команды README; реальный CLI
проверен в SDK. Публикация приложения не перезапускала. Из корня репозитория,
Python 3.12, новый путь вывода:

```powershell
Push-Location benchmarks/resilient-cli-suite-20261026-01/solutions/ledgerreconcile/A
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output demo-report.json
Pop-Location
Push-Location benchmarks/resilient-cli-suite-20261026-01/solutions/safezip/A
python -m safezip inspect examples/sample.zip
Pop-Location
```

У SafeZip B только `.gitignore`; рабочего демо для него нет. Всего сохранены 25
файлов приложений. Манифесты [Ledger](ledgerreconcile-publication.json) и
[SafeZip](safezip-publication.json) связывают точные исходники/verifier и семь
производных отчётов на задачу. [Метаданные](metadata-publication.json) добавляют
67 файлов: 16 точных runtime, шесть канонических входов и 45 производных отчётов.
Хеши исходных и опубликованных отчётов разделены.

Native auth/история общие; физическая изоляция чтения соседних веток ослаблена.
Базы, raw-логи, maps и stdout/stderr не публикуются. CLI 0.164.0-alpha.11.1
отличается от старых серий на 0.163; причинное объединение недопустимо.
Неизвестные общий usage, стоимость API и изменение квоты остаются null.
Проверки целостности сводки пройдены для обеих задач. У Ledger допустимое отношение
времени есть, у неудачного SafeZip его нет; среднее по незавершённой серии не
считается. Времена одного запуска не доказывают общего преимущества скорости или квоты.
