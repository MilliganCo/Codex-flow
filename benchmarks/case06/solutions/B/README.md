# ASCII Tree Explorer

Интерактивное процедурное дерево с общей геометрией для 2D, 3D и 4D.
Нужен Python 3.12+; сторонних runtime/test зависимостей, сети и GPU не требуется.

## Запуск

Из каталога проекта в Windows Terminal / PowerShell 7:

```powershell
python --version
python -m ascii_tree --help
python -m ascii_tree view --seed 42 --mode 3d
```

Установка пакетов не нужна. Можно заменить `python` на `py -3.12`, а на
Linux/WSL — на `python3`. Рекомендуются 100×40 ячеек и Cascadia Mono.
Размер берётся из терминала и отслеживается при resize.
Необязательный entrypoint `ascii-tree` объявлен в `pyproject.toml`; после
установки пакета он эквивалентен `python -m ascii_tree`. Основные команды ниже
проверены без установки. Build backend закреплён: `setuptools==80.9.0`.

## Управление

- `1` / `2` / `3`: 2D / 3D / 4D, без изменения дерева и seed.
- Стрелки: камера в 3D/4D; `[` / `]`: XW-поворот в 4D.
- `+` / `-`: масштаб (также `=` / `_`); `Space`: анимация / пауза.
- `G`: следующий seed; `R`: сброс ориентации, времени и масштаба; `B`: листва.
- `E`: экспорт; `H` / `?`: справка; `Q` / `Esc`: выход; `Ctrl+C`: выход с кодом 130.

Справка замораживает анимацию. В 2D камера фиксирована как вид спереди;
масштаб и остальные действия доступны. `R` сохраняет seed и режим.
`G` увеличивает seed на один; любой результат можно повторить по seed в заголовке.

`E` сохраняет текущий растр дерева без UI/ANSI в
`exports/tree-SEED-MODE-NNNN.txt`, не перезаписывая старые файлы.
Папка задаётся `view --export-dir my-frames`. В окне 100×40 растр имеет 100×35
ячеек: пять строк занимает UI. Справка в экспорт не попадает.

## Headless и экспорт

```powershell
python -m ascii_tree render --seed 42 --mode 2d --width 100 --height 40 --output tree-2d.txt
python -m ascii_tree render --seed 42 --mode 3d --yaw 65 --pitch 12 --output tree-3d.txt
python -m ascii_tree render --seed 42 --mode 4d --angle4d 0 --output before.txt
python -m ascii_tree render --seed 42 --mode 4d --angle4d 35 --output after.txt
python -m ascii_tree render --seed 7 --mode 3d --zoom 1.1 --time 2.5 --output seed7.txt
```

`render` работает без TTY. Без `--output` кадр пишется в stdout. Оба пути
выдают только печатаемый ASCII и LF, без BOM/ANSI: ровно width ячеек в каждой
из height строк, включая завершающие пробелы и LF после последней строки.
Одинаковые параметры дают одинаковые байты. `--output` исключает изменения
кодировки/переносов при перенаправлении средствами PowerShell.

Параметры: `--seed`, `--mode {2d,3d,4d}`, `--width`, `--height`, `--yaw`,
`--pitch`, `--angle4d`, `--zoom`, `--aspect`, `--time`, `--bare`.
Углы в градусах. `--time t` детерминированно добавляет `14*t` к yaw и `9*t`
к XW; в 2D время не меняет кадр. `--bare` отключает листву.
`--aspect` — высота ячейки / ширина, по умолчанию 2. Допустимы кадры
1×1–500×250, zoom 0.15–5, aspect 0.5–4. В viewer размеры следуют терминалу.
`view` без интерактивного stdin или stdout завершается с кодом 2 и подсказкой
использовать render. Ошибочные параметры/ошибки записи также дают код 2.

## Геометрия и 4D

Один неизменяемый граф содержит родительские связи, концы `(x,y,z,w)`, радиусы
и порядок ветвления. Локальный RNG порождает изогнутый сужающийся ствол,
корневые наплывы, пространственные ветви четырёх порядков и группы листьев.
Seed 42: 550 сегментов и 1042 листа.

2D — ортографическая проекция графа на XY; скелет кроны можно показать через B.
3D — вращение XYZ, перспективная камера и per-cell z-buffer: ближние ветви
перекрывают дальние независимо от порядка подачи. Shading зависит от глубины
и толщины. Aspect учитывает прямоугольность текстовых ячеек.

W — накопленное расстояние вдоль пути роста, начиная с −4.5; сегмент длины L
добавляет `0.52*L`. Это переменная координата возраста. В 4D после центрирования Y:

```text
x' = cos(a)*x - sin(a)*w
w' = sin(a)*x + cos(a)*w
y' = y, z' = z
(X,Y,Z) = (x',y',z') * 24 / (24 - w')
```

Затем XYZ проходит обычную 3D-камеру и проекцию в терминал. XW-поворот
сохраняет 4D-норму, определитель матрицы равен 1. При 90°: `x'=-w`, `w'=x`.
Точки разного возраста движутся по-разному. Интерфейс прямо сообщает:
терминал показывает проекцию 4D-данных, цепочка `4D -> 3D -> 2D`.

## Проверки и примеры

Smoke одной конечной командой (около 4 секунд в текущем окружении):

```powershell
python scripts/smoke.py
```

Он запускает suite и побайтную сверку сохранённых кадров. Отдельные команды:

```powershell
python -m unittest discover -s tests -v
python scripts/generate_samples.py --check
python scripts/check_console.py
python scripts/benchmark.py
```

Console probe требует настоящий TTY: показывает один кадр, проверяет
восстановление console modes после выхода и исключения, сохраняет
`artifacts/console-probe.json`. Без TTY честно сообщает NOT RUN.

В [samples](samples/) находятся 2D, 3D, 4D XW 0°/35° для seed 42 и 3D seed 7;
[manifest.json](samples/manifest.json) хранит параметры и SHA-256.
Пересоздание: `python scripts/generate_samples.py`.
Интерактивный сценарий: [DEMO.md](DEMO.md).
Решения: [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md).
Результаты и ограничения: [VERIFICATION.md](VERIFICATION.md).
