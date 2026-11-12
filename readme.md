# BookGenerator - bgen

Генератор цифровых книг из Markdown. Собирает FB2/EPUB/DOCX),
дополняя Pandoc постобработкой: эпиграфы, аннотации, кавычки, фронтиспис,
`document-info` и т.д. — то, что Pandoc не умеет или делает невалидно.

## Требования

- **Python 3.9+** (для `ET.indent`; на более старых версиях форматирование
  XML пропускается с предупреждением).
- **Pandoc** в `PATH`. Проверено на 3.1.3.
- **PyYAML**: `pip install pyyaml`.
- **lxml**: `pip install lxml` (для XSD-валидации FB2).

## Установка

bgen распространяется как дистрибутив: `bgen.py`, `lib_bgen.py`,
`filter_bgen.lua`, `abbrevs.txt`, `config.schema.json` (когда появится)
и `schemas/` (XSD FB2) лежат рядом. Копировать файлы по отдельности не нужно —
используйте дистрибутив как есть.

`schemas/` содержит `FictionBook.xsd` и связанные схемы. Без них `build`
упадёт с `BgenError`: валидация FB2 по XSD обязательна.

## Быстрый старт

cp -r project_sample mybook
cd mybook

отредактировать config.yaml и текст в body/

./bgen.py build <path_to_project>
./bgen.py stat <path_to_project>

Результат — output/book.fb2.

bgen.py --help
bgen.py build <path> [--only fb2]   # собрать книгу
bgen.py stat <path>                 # статистика текста (файлы, знаки, слова)

stat — только объёмные метрики. Анализ стиля (повторы, частотность) — вне
bgen (отдельный инструмент).

Примеры разметки и их результат в FB2 — в project\_sample/body/99\_syntax\_demo.md
Соберите пример и посмотрите результат.

