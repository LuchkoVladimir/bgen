# TODO / План развития bgen

## Высокий приоритет

### upd? title-date не хватает lang

### Пройтись по fb2
- нужно чтобы была возможность задать всё допустимое из поддержаных сейчас параметров (lang и т.д.)
    - что не поддержано - это через xml
- title-info / book-title : lang                                            book-title-lang
- title-info / annotation : lang                                            annotation-lang
- document-info / author (только один скопирован)                           copy-first / настройка как title-author
    + doc-author
- document-info / program-used :                                            lang -- генерировать вместе с text?
- document-info / date : генерится value=text, нет lang                     defs/refs в schema? и func в python?
    date -> doc-date

### Полировка readme.md и примера md
- перед выкладкой на github


## Средний приоритет

### stat
- author + title
- существующий stat
- структура по md в body - заголовки всех уровней и размеры глав.

<authors>
<title>

totals:
chars:
words:
files:

annotation: chars-words
epigraph: chars-words

chars-words section 1     
chars-words subsection 1.1
chars-words subsection 1.2
chars-words section 2     
chars-words subsection 2.1
chars-words subsection 2.2

### check
- чек конфиги на валидность (тут же и резолвинг указанных файлов)
- чек на наличие ресурсов (картинок), указанных в md.

<authors>
<title>

images:
cover:     found : path0
           found : path1
           found : path2
       not found : path3
...

build files:
fb2-xml:    off   :
epub-css:   bgen  : <path>
epub-xml:   off   :
docx-ref:   found : <path>
typography: bgen  : <path>

body order:
file1
file2
file3
...

### cfg
- вывод конфиги

<authors>
<title>

config:
...

### typo
- чек на типографию - поиск ", шаблонов " - " и прочих без нужных пробелов и т. д.
- описать правила в readme

<authors>
<title>

<RULE XX: pattern in human style 1>:
- ent1
- ent2
- ent3
...
<RULE YY: pattern in human style 2>:
- ent1
- ent2
- ent3
...
<...>

### Тесты (pytest)
**Что:** тесты на `_make_book_id`, `_apply_custom_description`,
`_update_book_anno_and_epi_from_body`, `_sort_children_by_order`, фильтр
(через вызов Pandoc на минимальном проекте).
**Зачем:** без тестов изменения в постобработке могут сломать FB2 незаметно.
**Сложность:** средняя.


## Низкий приоритет (отложено)

### Валидация через `xmlschema` вместо `lxml`
**Что:** `xmlschema` показывает **все** ошибки XSD, а не первую.
**Зачем:** удобство отладки.
**Сложность:** низкая.

### Карточка книги
**Что:** 
    Что: команда bgen.py info <path>, которая выводит (в JSON или YAML) все метаданные книги: title, author, genres,
    lang, id, date, sequence, keywords, cover path. Это то, что нужно для публикации на платформах (Kobo, Amazon KDP,
    ЛитРес) — заполнение полей «название», «серия», «жанр», «ISBN».-2-5
**Зачем:** 
    Это мост к публикации. Если bgen генерирует sequence, логично, чтобы он же выводил её для копирования в Kobo/Amazon.
    Генерация «карточки книги» (book card / metadata export)
**Сложность:** средняя. Пока не было необходимости.

### Стили (`style` и `<stylesheet>`)
**Что:** `::: {.style name="letter"}` → `<p style="letter">`, плюс
`<stylesheet>` в `description`.
**Зачем:** письма, документы, телеграммы в художке; «врезки» в публицистике.
**Сложность:** высокая, непредсказуемо в читалках.

### Таблицы с colspan/rowspan
**Что:** либо ограничиться простыми таблицами (задокументировать), либо
постобработка (хрупко).
**Зачем:** в публицистике — обычное дело.
**Сложность:** высокая (ограничение Pandoc).

### EPUB dtb:depth = 1, что может не отражать реальность
Проблема в том, что Pandoc (в версии 3.1.3, которую вы используете) жёстко ставит dtb:depth = 1, даже если в navMap
есть вложенные navPoint (у вас — уровень 2 для подразделов «Демонстрации синтаксиса»). Это не ошибка вашего кода,
а поведение Pandoc.

---

## Не делать

- **Spellcheck** — есть сторонние сервисы с недостижимым качеством.
- **PDF для печати** — ручная работа (формат полосы, поля, шрифты, висячие
  строки). Максимум — DOCX с чистыми стилями как заготовка для верстальщика.
- **Планирование/outlining, focus mode, синхронизация/облако, AI-ассистент** —
  это не про сборку книги. `bgen` не должен становиться редактором.
- **Проверка повторов слов, частотность сверх топ-20, «стилевые» рекомендации** —
  это редакторские инструменты, вне концепции `bgen` (отдельный скрипт).
- **MOBI/AZW3** — Amazon сам конвертирует EPUB при Send to Kindle.
- **Мерж `fb2_description.xml` с `config.yaml`** — `template` покрывает 90% случаев.
- **Фронтиспис для docx** - Это редакторский формат. Морока того не стоит.

