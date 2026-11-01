# bgen

Генератор цифровых книг из Markdown. Собирает FB2 с корректным тегированием,
дополняя то, что Pandoc не умеет делать сам (эпиграфы, стихи, астеризмы,
жанры, аннотация, document-info).

## Требования

- **Python 3.9+** (для `ET.indent`; на более старых версиях форматирование
  XML пропускается с предупреждением).
- **Pandoc** в `PATH`. Проверено на 3.1.3.
- **PyYAML**: `pip install pyyaml`.

## Установка

Скопируйте `bgen.py`, `lib_bgen.py` и `abbrevs.txt` в удобное место.
Запускайте `bgen.py` из этой директории (или добавьте её в `PATH`).

## Быстрый старт

```bash
cp -r project_sample mybook
cd mybook
# отредактировать config.yaml и текст в body/
python3 /path/to/bgen/bgen.py build .
python3 /path/to/bgen/bgen.py stat .
```

Результат — output/book.fb2.

## Команды

```bash
bgen --help
```

