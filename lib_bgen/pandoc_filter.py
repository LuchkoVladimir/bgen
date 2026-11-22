#!/usr/bin/env python3

# pandoc_filter.py
# Превращает fenced div'ы bgen в FB2-теги для writer'а fb2.
# Также обрабатывает Span (типографика: [min]{.t}, [текст]{.q} и т.д.)
#
# Copyright (C) 2026 Владимир Лучко
# This program is free software: you can redistribute it and/or modify it under the terms
# of the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this program.
# If not, see https://www.gnu.org/licenses/.

import os
import re
import panflute as pf

from functools import cache
from pathlib import Path

# ============================================================
# Типографика: читает typography.txt (separator=:)
# ============================================================

@cache
def get_typography() -> dict[str, dict]:
    path = Path(os.environ.get("BGEN_TYPOGRAPHY"))
    lines = path.read_text(encoding="utf-8").splitlines()

    sep = None
    entries: dict[str, dict] = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if m := re.match(r"^separator=(.)\s*$", line):
            sep = m.group(1)
            continue
        if sep is None:
            continue

        parts = line.split(sep)
        match parts:
            case [key, value] if key and value:
                entries[key] = {"kind": "single", "value": value}
            case [key, open_q, close_q] if key and open_q and close_q:
                entries[key] = {"kind": "pair", "open_q": open_q, "close_q": close_q}

    return entries


# Span: типографика.
# .t — одиночная замена: [min]{.t} → − (текст = ключ в typography.txt).
# .q/.qq/.qqq — парная замена: [текст]{.q} → «текст».
def span(elem: pf.Span, doc: pf.Doc) -> list[pf.Inline] | None:
    entries = get_typography()
    if not entries:
        return None

    classes = set(elem.classes)

    # .t: одиночная замена (текст = ключ)
    if "t" in classes:
        text = pf.stringify(elem)
        entry = entries.get(text)
        if entry and entry["kind"] == "single":
            return pf.Str(entry["value"])
        return None

    # Парные: [текст]{.key} → open + content + close
    for key, entry in entries.items():
        if key in classes and entry["kind"] == "pair":
            return [pf.Str(entry["open_q"]), *elem.content, pf.Str(entry["close_q"])]
    return None


# Разворачивает верхнеуровневый <tag> внутри контейнера (epigraph/annotation):
# запоминает содержимое тега, кладёт его на место родителя.
def unwrap_top_tag(body: str, tag: str) -> str:
    open_re = re.compile(rf"<{tag}[^>]*>")
    close_re = re.compile(rf"</{tag}>")

    m = open_re.search(body)
    if not m:
        return body

    depth = 1
    pos = m.end()
    while depth > 0:
        o = open_re.search(body, pos)
        c = close_re.search(body, pos)
        if not c:
            return body
        if o and o.start() < c.start():
            depth += 1
            pos = o.start() + 1
        else:
            depth -= 1
            if depth == 0:
                return body[m.end():c.start()]
            pos = c.start() + 1
    return body


# Сериализует один блок в FB2-строку и разворачивает верхнеуровневую секцию.
def render_one_block(block: pf.Block) -> str:
    doc = pf.Doc(block, metadata={})
    fb2_text = pf.convert_text(
        doc, input_format="panflute", output_format="fb2"
    )
    start = fb2_text.find("<body>")
    end = fb2_text.find("</body>")
    body = fb2_text[start + len("<body>"):end] if start != -1 and end != -1 else fb2_text
    return unwrap_top_tag(body, "section")


# Сериализует список блоков, обрабатывая каждый отдельно.
def render_blocks(blocks: list[pf.Block]) -> str:
    return "\n".join(
        r for b in blocks if (r := render_one_block(b))
    )


def div(elem: pf.Div, doc: pf.Doc) -> pf.Block | list[pf.Block] | None:
    classes = set(elem.classes)
    fmt = doc.format

    # EPUB: asterism
    if "epub" in fmt:
        if "asterism" in classes:
            d = pf.Div(pf.Para(pf.Str("* * *")))
            d.attributes["class"] = "asterism"
            return d
        return None

    # DOCX: custom-style для стилей из reference.docx
    if fmt == "docx":
        if "epigraph" in classes:
            elem.attributes["custom-style"] = "Epigraph"
            return elem
        elif "text-author" in classes:
            elem.attributes["custom-style"] = "EpigraphAuthor"
            return elem
        elif "annotation" in classes:
            elem.attributes["custom-style"] = "Abstract"
            return elem
        elif "subtitle" in classes:
            elem.attributes["custom-style"] = "Subtitle"
            return elem
        elif "asterism" in classes:
            d = pf.Div(pf.Para(pf.Str("* * *")))
            d.attributes["custom-style"] = "Asterism"
            return d
        elif "gap" in classes:
            d = pf.Div(pf.Para())
            d.attributes["custom-style"] = "Gap"
            return d
        return None

    # TXT: asterism и gap
    if fmt == "plain":
        if "asterism" in classes:
            return pf.Para(pf.Str("* * *"))
        elif "gap" in classes:
            return pf.Para(pf.Str("- -"))
        return None

    if fmt != "fb2":
        return None

    # .annotation: аннотация секции
    if "annotation" in classes:
        inner = render_blocks(elem.content)
        return pf.RawBlock(f"<annotation>{inner}</annotation>", format="fb2")

    # .frontispiece: фронтиспис (книги) --- картинка перед title в body
    if "frontispiece" in classes:
        return None  # оставляем Div как есть, Pandoc разберётся

    # .epigraph: эпиграф (книги или главы)
    if "epigraph" in classes:
        inner = render_blocks(elem.content)
        return pf.RawBlock(f"<epigraph>{inner}</epigraph>", format="fb2")

    # .text-author: автор эпиграфа
    if "text-author" in classes:
        text = pf.stringify(elem).rstrip()
        return pf.RawBlock(f"<text-author>{text}</text-author>", format="fb2")

    # .subtitle: смысловой разделитель внутри секции
    if "subtitle" in classes:
        inner = render_blocks(elem.content)
        inner = unwrap_top_tag(inner, "p")
        return pf.RawBlock(f"<subtitle>{inner}</subtitle>", format="fb2")

    # .asterism: сильный разделитель
    if "asterism" in classes:
        return [
            pf.RawBlock("<empty-line/>", format="fb2"),
            pf.RawBlock("<p>* * *</p>", format="fb2"),
            pf.RawBlock("<empty-line/>", format="fb2"),
        ]

    # .gap: слабый разделитель
    if "gap" in classes:
        return [pf.RawBlock("<empty-line/>", format="fb2")]

    return None


# LineBlock (стихи через |): для DOCX оборачиваем в Div с custom-style="Poem",
# чтобы Pandoc применил стиль Poem из reference.docx.
# Для FB2 не трогаем (Pandoc сам делает <poem><stanza><v>).
def line_block(elem: pf.LineBlock, doc: pf.Doc) -> pf.Div | None:
    fmt = doc.format
    if "epub" in fmt:
        d = pf.Div(elem)
        d.attributes["class"] = "poem"
        return d
    if fmt == "docx":
        d = pf.Div(elem)
        d.attributes["custom-style"] = "Poem"
        return d
    return None


def action(elem: pf.Element, doc: pf.Doc) -> pf.Element | list[pf.Element] | None:
    match elem:
        case pf.Div():
            return div(elem, doc)
        case pf.Span():
            return span(elem, doc)
        case pf.LineBlock():
            return line_block(elem, doc)
    return None


def main(doc: pf.Doc | None = None) -> pf.Doc | None:
    return pf.run_filter(action, doc=doc)


if __name__ == "__main__":
    main()


