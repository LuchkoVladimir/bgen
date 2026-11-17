"""FB2: постобработка сгенерированного Pandoc XML."""
from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as ET
from datetime import date as date_cls
from pathlib import Path

from ..common import (
        BgenError,
        PROGRAM_NAME,
        PROGRAM_TITLE,
        PROGRAM_VERSION,
)

PROGRAM_USED = f"{PROGRAM_TITLE}: {PROGRAM_NAME}-{PROGRAM_VERSION}"

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_TITLE_INFO_ORDER = [
    "genre", "author", "book-title", "annotation", "keywords",
    "date", "coverpage", "lang", "src-lang", "translator", "sequence",
]
_DOC_INFO_ORDER = [
    "author", "program-used", "date", "src-url", "src-ocr",
    "id", "version", "history", "publisher",
]


def _make_book_id(config: dict) -> str:
    """Возвращает id книги: явный из fb2.id или UUID5 от title+author+lang."""
    fb2_cfg = config.get("fb2") or {}
    explicit = fb2_cfg.get("id")
    if explicit:
        return str(explicit)

    meta = config.get("metadata") or {}
    title = meta.get("title", "")
    authors = meta.get("author") or []
    if isinstance(authors, list):
        author_str = "|".join(str(a) for a in authors)
    else:
        author_str = str(authors)
    lang = meta.get("lang", "ru")
    key = f"{title}|{author_str}|{lang}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _sort_children_by_order(parent: ET.Element, order: list[str]) -> None:
    """Переставляет дочерние элементы parent в порядке order.

    Элементы, которых нет в order, идут в конец, сохраняя относительный порядок.
    """
    ns = FB2_NS
    children = list(parent)
    order_idx = {f"{{{ns}}}{name}": i for i, name in enumerate(order)}
    children.sort(key=lambda el: order_idx.get(el.tag, len(order)))
    for child in list(parent):
        parent.remove(child)
    for child in children:
        parent.append(child)


def _update_book_elements_from_body(body: ET.Element, title_info: ET.Element) -> None:
    """За один проход по <body>: переносит <annotation>, <image> и <epigraph>
    из безымянных секций в <title-info> и <body> соответственно.

    Безымянная секция (без <title>) — признак элемента книжного уровня:
    Pandoc оборачивает эпиграф/фронтиспис/аннотацию книги, стоящие до первого
    заголовка, в <section> без <title>. Если секция с <title> — это
    эпиграф/аннотация/фронтиспис главы, их не трогаем (схема FB2 это разрешает).
    """
    ns = {"fb": FB2_NS}

    blank_sections = [
        s for s in body.findall("fb:section", ns)
        if s.find("fb:title", ns) is None
    ]
    if len(blank_sections) > 1:
        raise BgenError(
            f"Pandoc сгенерировал {len(blank_sections)} безымянных секций, "
            f"ожидалась одна (для аннотации/эпиграфа книги)"
        )

    # Собираем аннотацию, фронтиспис и эпиграфы книги в безымянной секции
    book_annotations = []
    book_epigraphs = []
    book_fronts = []

    if blank_sections:
        section = blank_sections[0]
        book_annotations = list(section.findall("fb:annotation", ns))
        for ann in book_annotations:
            section.remove(ann)
        book_epigraphs = list(section.findall("fb:epigraph", ns))
        for ep in book_epigraphs:
            section.remove(ep)
        book_fronts = list(section.findall("fb:image", ns))
        for fp in book_fronts:
            section.remove(fp)
        leftover = [c for c in section]
        if leftover:
            raise BgenError(
                f"в безымянной секции после переноса annotation/epigraph "
                f"осталось содержимое: {[c.tag for c in leftover]}"
            )
        body.remove(section)

    # Проверка: image может быть только один
    if len(book_fronts) > 1:
        raise BgenError(
            f"в <body> может быть только один <image> (фронтиспис), "
            f"найдено {len(book_fronts)}"
        )
    if book_fronts:
        body.insert(0, book_fronts[0])

    # Вставляем аннотацию книги в <title-info>, собирая одну общую из нескольких, если их было много
    if book_annotations:
        for old in title_info.findall("fb:annotation", ns):
            title_info.remove(old)
        ann = ET.SubElement(title_info, f"{{{FB2_NS}}}annotation")
        for annotation_el in book_annotations:
            for child in list(annotation_el):
                ann.append(child)

    # Находим индекс куда вставлять эпиграфы (первой <section> в body или конца body, если нет <section>)
    first_section_idx = len(body)
    for i, child in enumerate(body):
        if child.tag == f"{{{FB2_NS}}}section":
            first_section_idx = i
            break

    # Вставляем эпиграфы после image/title
    for offset, ep in enumerate(book_epigraphs):
        body.insert(first_section_idx + offset, ep)


def _apply_custom_description(
    root: ET.Element,
    config: dict,
    desc_path: Path | None,
    generated_title_info: ET.Element,
    generated_doc_info: ET.Element,
    warnings: list[str],
) -> None:
    """Применяет fb2_description.xml в режиме template или override.

    auto     — ничего не делает.
    template — обходит ШАБЛОН; для каждого элемента, который есть и в шаблоне,
               и в сгенерированном description, заменяет содержимое шаблона
               на сгенерированное. Новых элементов не добавляет.
    override — заменяет <description> целиком на содержимое файла.
    """
    fb2_cfg = config.get("fb2") or {}
    mode = fb2_cfg.get("description-mode", "auto")
    if mode == "auto":
        return

    try:
        custom_tree = ET.parse(desc_path)
    except ET.ParseError as e:
        raise BgenError(f"не удалось разобрать {desc_path}: {e}")

    custom_root = custom_tree.getroot()
    if custom_root.tag != f"{{{FB2_NS}}}description":
        found = None
        for el in custom_tree.iter():
            if el.tag == "description" or el.tag.endswith("}description"):
                found = el
                break
        if found is None:
            raise BgenError(f"в {desc_path} не найден <description>")
        custom_root = found

    if mode == "override":
        old_desc = root.find(f"{{{FB2_NS}}}description")
        if old_desc is not None:
            idx = list(root).index(old_desc)
            root.remove(old_desc)
            root.insert(idx, custom_root)
        else:
            root.insert(0, custom_root)
        warnings.append(
            "fb2.description-mode=override: значения config.yaml для description "
            "(author, book-title, genre, date, annotation, coverpage, lang) "
            "игнорируются"
        )
        return

    # template: обходим шаблон (dst), заполняем из сгенерированного (src).
    ns = FB2_NS

    def merge_by_template(src_parent: ET.Element, dst_parent: ET.Element) -> None:
        """Для каждого тега, который есть в dst_parent И в src_parent,
        удаляет все элементы с этим тегом в dst_parent и вставляет все
        элементы с этим тегом из src_parent на место первого удалённого.
        Если тега нет в src — оставляет как в шаблоне (не трогает).
        Если тега нет в dst — не добавляет (шаблон решает, что будет).
        """
        # Уникальные теги в порядке появления в dst
        seen = []
        for child in dst_parent:
            if child.tag not in seen:
                seen.append(child.tag)

        for tag in seen:
            src_children = [c for c in src_parent if c.tag == tag]
            if not src_children:
                continue  # bgen не генерирует это поле — оставляем из шаблона
            dst_children = dst_parent.findall(tag)
            first_idx = list(dst_parent).index(dst_children[0])
            for c in dst_children:
                dst_parent.remove(c)
            for offset, src_child in enumerate(src_children):
                dst_parent.insert(first_idx + offset, copy.deepcopy(src_child))

    custom_ti = custom_root.find(f"{{{ns}}}title-info")
    if custom_ti is not None:
        merge_by_template(generated_title_info, custom_ti)

    custom_di = custom_root.find(f"{{{ns}}}document-info")
    if custom_di is not None:
        merge_by_template(generated_doc_info, custom_di)

    # Заменяем description в root
    old_desc = root.find(f"{{{FB2_NS}}}description")
    if old_desc is not None:
        idx = list(root).index(old_desc)
        root.remove(old_desc)
        root.insert(idx, custom_root)
    else:
        root.insert(0, custom_root)


def _fb2_deduplicate_binaries(root: ET.Element) -> None:
    """Удаляет дубликаты <binary> с одинаковым содержимым,
    перенаправляя ссылки xlink:href на оставшийся id.
    """
    XLINK_NS = "http://www.w3.org/1999/xlink"

    # Карта: base64-содержимое -> id первого встреченного binary
    seen: dict[str, str] = {}
    # Карта: старый id -> новый id (для ссылок)
    id_map: dict[str, str] = {}
    to_remove: list[ET.Element] = []

    for binary in root.findall(f"{{{FB2_NS}}}binary"):
        binary_id = binary.get("id")
        content = (binary.text or "").strip()
        if not binary_id or not content:
            continue

        if content in seen:
            # Дубликат: запоминаем, что старый id теперь указывает на новый
            id_map[binary_id] = seen[content]
            to_remove.append(binary)
        else:
            seen[content] = binary_id

    if not to_remove:
        return

    # Удаляем дубликаты
    for binary in to_remove:
        root.remove(binary)

    # Перенаправляем ссылки
    for el in root.iter():
        href = el.get(f"{{{XLINK_NS}}}href")
        if href and href.startswith("#"):
            old_id = href[1:]
            if old_id in id_map:
                el.set(f"{{{XLINK_NS}}}href", f"#{id_map[old_id]}")


def _fix_fb2_pandoc_bugs(root: ET.Element) -> None:
    """Исправляет известные баги Pandoc FB2-writer:
    пустые <emphasis>/<p> после таблиц, xlink:type, дубликаты <binary>.
    """
    # Известный баг Pandoc: пустой <emphasis /> после таблиц.
    # Именно в этом порядке! (<p><emphasis /></p>)
    # Шаг 1: пустые <emphasis>
    for emph in list(root.iter(f"{{{FB2_NS}}}emphasis")):
        if not (emph.text or "").strip() and len(emph) == 0:
            for parent in root.iter():
                if emph in list(parent):
                    parent.remove(emph)
                    break

    # Шаг 2: пустые <p> (после удаления emphasis)
    for p in list(root.iter(f"{{{FB2_NS}}}p")):
        if not (p.text or "").strip() and len(p) == 0:
            for parent in root.iter():
                if p in list(parent):
                    parent.remove(p)
                    break

    # Pandoc генерирует xlink:type="inlineImageType"/"imageType",
    # схема FB2 требует fixed value "simple".
    XLINK_NS = "http://www.w3.org/1999/xlink"
    for el in root.iter():
        xlink_type = el.get(f"{{{XLINK_NS}}}type")
        if xlink_type is not None and xlink_type != "simple":
            el.set(f"{{{XLINK_NS}}}type", "simple")

    # Если одна картинка добавлена в книгу несколько раз, то pandoc
    # создаёт binary для каждого вхождения
    _fb2_deduplicate_binaries(root)


def _check_fb2_affecting_sections(root: ET.Element) -> tuple[ET.Element, ET.Element, ET.Element]:
    """Проверяет наличие секций, в которые bgen будет вносить изменения.
    Возвращает (title_info, document_info, body).
    Бросает BgenError, если чего-то нет.
    """
    ns = {"fb": FB2_NS}

    description = root.find("fb:description", ns)
    if description is None:
        raise BgenError("description не найден в сгенерированном pandoc FB2")

    title_info = description.find("fb:title-info", ns)
    if title_info is None:
        raise BgenError("title-info не найден в сгенерированном pandoc FB2")

    doc_info = description.find("fb:document-info", ns)
    if doc_info is None:
        raise BgenError("document-info не найден в сгенерированном pandoc FB2")

    body = root.find("fb:body", ns)
    if body is None:
        raise BgenError("body не найден в сгенерированном pandoc FB2")

    return title_info, doc_info, body


def _write_fb2(
    tree: ET.ElementTree,
    print_mode: src,
    fb2_path: Path,
    warnings: list[str],
) -> None:
    """Форматирование XML по режиму print и запись файла.

    pretty  — indent 2 пробела.
    toleft  — indent "" (без пробелов, но с \n).
    src     — indent "" (как toleft).
    """
    if print_mode in ("pretty", "toleft", "src"):
        space = "  " if print_mode == "pretty" else ""
        try:
            ET.indent(tree, space=space, level=0)
        except AttributeError:
            warnings.append("ET.indent недоступен (Python < 3.9), форматирование пропущено")

    tree.write(fb2_path, encoding="utf-8", xml_declaration=True)


def _update_metadata_genres(fb2_cfg: dict, title_info: ET.Element) -> None:
    """Заменяет <genre> в title-info на жанры из config.yaml (или unrecognised)."""
    ns = {"fb": FB2_NS}

    for g in title_info.findall("fb:genre", ns):
        title_info.remove(g)
    for g in fb2_cfg.get("genres") or ["unrecognised"]:
        if isinstance(g, dict):
            name = g.get("name")
            if not isinstance(name, str) or not name:
                raise BgenError(
                    f"fb2.genres: 'name' должен быть непустой строкой, получено {name!r}"
                )
            match = g.get("match")
            if match is not None:
                if not (type(match) is int) or not (1 <= match <= 100):
                    raise BgenError(
                        f"fb2.genres: 'match' должен быть целым числом 1..100, получено {match!r}"
                    )
            genre_el = ET.SubElement(title_info, f"{{{FB2_NS}}}genre")
            genre_el.text = name
            if match is not None:
                genre_el.set("match", str(match))
        elif isinstance(g, str):
            ET.SubElement(title_info, f"{{{FB2_NS}}}genre").text = g
        else:
            raise BgenError(f"fb2.genres: ожидается строка или словарь, получено {type(g).__name__}")


def _update_metadata_authors(fb2_cfg: dict, title_info: ET.Element, doc_info: ET.Element) -> None:
    """Обновляет title-info/author (если задано в config.yaml) и, при
    doc-author-copy-first-from-title, копирует первого автора в document-info.
    """

    def _is_valid_author_dict(a: dict) -> bool:
        """Проверяет, что словарь автора соответствует одному из вариантов FB2:
        nickname [+ any], либо first-name + last-name [+ any].
        """
        if a.get("nickname"):
            return True
        return bool(a.get("first-name") and a.get("last-name"))

    ns = {"fb": FB2_NS}
    title_authors = fb2_cfg.get("title-author") or []

    # Нормализуем: убираем пустые строки и невалидные словари
    title_authors = [
        a for a in title_authors
        if (isinstance(a, str) and a.strip())
        or (isinstance(a, dict) and _is_valid_author_dict(a))
    ]
    if title_authors:
        # Удаляем сгенерированных Pandoc'ом авторов
        for old in title_info.findall("fb:author", ns):
            title_info.remove(old)

        for author in title_authors:
            if isinstance(author, str):
                words = author.split()
                author_el = ET.SubElement(title_info, f"{{{FB2_NS}}}author")
                if len(words) == 1:
                    ET.SubElement(author_el, f"{{{FB2_NS}}}nickname").text = words[0]
                elif len(words) == 2:
                    ET.SubElement(author_el, f"{{{FB2_NS}}}first-name").text = words[0]
                    ET.SubElement(author_el, f"{{{FB2_NS}}}last-name").text = words[1]
                else:
                    ET.SubElement(author_el, f"{{{FB2_NS}}}first-name").text = words[0]
                    ET.SubElement(author_el, f"{{{FB2_NS}}}middle-name").text = " ".join(words[1:-1])
                    ET.SubElement(author_el, f"{{{FB2_NS}}}last-name").text = words[-1]
            elif isinstance(author, dict):
                author_el = ET.SubElement(title_info, f"{{{FB2_NS}}}author")
                # Одиночные поля --- Имя, отчество, фамилия, никнейм (в этом порядке)
                for field in ("first-name", "middle-name", "last-name", "nickname"):
                    val = author.get(field)
                    if val:
                        ET.SubElement(author_el, f"{{{FB2_NS}}}{field}").text = str(val)
                # Множественные поля --- home-page, email (порядок!)
                for field in ("home-page", "email"):
                    values = author.get(field) or []
                    if isinstance(values, str):
                        values = [values]
                    for v in values:
                        if v:
                            ET.SubElement(author_el, f"{{{FB2_NS}}}{field}").text = str(v)
                # id - идёт последним
                if author.get("id"):
                    ET.SubElement(author_el, f"{{{FB2_NS}}}id").text = str(author["id"])
            else:
                raise BgenError(
                    f"fb2.title-author: ожидается строка или словарь, "
                    f"получено {type(author).__name__}"
                )

    copy_author = fb2_cfg.get("doc-author-copy-first-from-title", False)
    if copy_author:
        first_title_author = title_info.find("fb:author", ns)
        if first_title_author is not None:
            doc_info.append(copy.deepcopy(first_title_author))


def _update_metadata_title_date(fb2_cfg: dict, title_info: ET.Element) -> None:
    """Добавляет title-info/date из fb2.title-date (строка или {value, text})."""
    title_date = fb2_cfg.get("title-date")
    if title_date:
        if isinstance(title_date, dict):
            value = title_date.get("value")
            text = title_date.get("text") or value
            if not value:
                raise BgenError(
                    "fb2.title-date: словарь должен содержать 'value' (ISO)"
                )
        else:
            value = str(title_date)
            text = value

        date_el = ET.SubElement(
            title_info, f"{{{FB2_NS}}}date", {"value": str(value)}
        )
        date_el.text = str(text)


def _update_metadata_sequence(fb2_cfg: dict, title_info: ET.Element) -> None:
    """Добавляет title-info/sequence из fb2.sequence (строка или {name, number, lang})."""
    sequences = fb2_cfg.get("sequence") or []
    for seq in sequences:
        if isinstance(seq, str):
            if not seq:
                continue
            ET.SubElement(title_info, f"{{{FB2_NS}}}sequence", {"name": seq})
        elif isinstance(seq, dict):
            if not seq.get("name"):
                raise BgenError(
                    f"fb2.sequence: словарь должен содержать 'name', получено {seq!r}"
                )
            attrs = {"name": str(seq["name"])}
            if seq.get("number") is not None:
                attrs["number"] = str(seq["number"])
            if seq.get("lang"):
                attrs[f"{{{XML_NS}}}lang"] = str(seq["lang"])
            ET.SubElement(title_info, f"{{{FB2_NS}}}sequence", attrs)
        else:
            raise BgenError(
                f"fb2.sequence: ожидается строка или словарь, "
                f"получено {type(seq).__name__}"
            )


def _update_metadata(config: dict, title_info: ET.Element, doc_info: ET.Element) -> None:
    """Заполняет title-info и document-info значениями из config.yaml."""
    fb2_cfg = config.get("fb2") or {}
    ns = {"fb": FB2_NS}

    # title-info/genre --- обязателен, может быть несколько и с атрибутом match
    _update_metadata_genres(fb2_cfg, title_info)

    # title-info/author --- детальная настройка. Если пусто --- оставляем Pandoc-овского.
    # document-info/author --- копируем первого из title, если указано в настройках
    _update_metadata_authors(fb2_cfg, title_info, doc_info)

    # title-info/keywords --- опциональны, удобны для позиционирования наряду с жанрами, список строк через запятую
    keywords = fb2_cfg.get("keywords") or []
    if keywords:
        for old in title_info.findall("fb:keywords", ns):
            title_info.remove(old)
        kw_el = ET.SubElement(title_info, f"{{{FB2_NS}}}keywords")
        kw_el.text = ", ".join(str(k) for k in keywords)

    # title-info/date --- опциональна, но отображается в читалках, так что лучше заполнить
    _update_metadata_title_date(fb2_cfg, title_info)

    # title-info/sequence --- может быть несколько
    _update_metadata_sequence(fb2_cfg, title_info)

    # document-info/program-used --- pandoc генерирует свой, но мы пишем себя, так как включаем постобработку
    program_el = doc_info.find("fb:program-used", ns)
    if program_el is None:
        program_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}program-used")
    program_el.text = PROGRAM_USED

    # document-info/id --- обязателен
    book_id = _make_book_id(config)
    id_el = doc_info.find("fb:id", ns)
    if id_el is None:
        id_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}id")
    id_el.text = book_id

    # document-info/version --- обязательна
    version_val = fb2_cfg.get("version") or "1.0"
    version_el = doc_info.find("fb:version", ns)
    if version_el is None:
        version_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}version")
    version_el.text = str(version_val)

    # document-info/date --- обязательна
    date_val = fb2_cfg.get("date") or date_cls.today().isoformat()
    for old in doc_info.findall("fb:date", ns):
        doc_info.remove(old)
    ET.SubElement(doc_info, f"{{{FB2_NS}}}date", {"value": date_val}).text = date_val


def _postprocess_fb2(
    fb2_path: Path,
    config: dict,
    desc_path: Path | None,
    warnings: list[str],
) -> None:
    """Постобработка сгенерированного Pandoc FB2.

    warnings - внешний, для добавления предупреждений
    Шаги: проверка секций → фикс багов Pandoc → перенос книжных элементов
    из <body> → метаданные → сортировка → fb2_description.xml → запись.
    """
    ET.register_namespace("", FB2_NS)

    tree = ET.parse(fb2_path)
    root = tree.getroot()

    # Проверяем нужные нам для работы элементы структуры fb2 и получаем их из дерева
    title_info, doc_info, body = _check_fb2_affecting_sections(root)

    # Фикс известных багов
    _fix_fb2_pandoc_bugs(root)

    # В bgen мы пишем аннотацию, фронтиспис и эпиграф перед первой секцией, чтобы pandoc обработал md. Теперь нужно
    # достать из созданной pandoc`ом для них секции и разместить где нужно
    _update_book_elements_from_body(body, title_info)

    # Заполняем метадату по конфиге
    _update_metadata(config, title_info, doc_info)

    # Приводим порядок в соответствие со схемой FB2
    _sort_children_by_order(title_info, _TITLE_INFO_ORDER)
    _sort_children_by_order(doc_info, _DOC_INFO_ORDER)

    # fb2_description.xml (template / override)
    _apply_custom_description(root, config, desc_path, title_info, doc_info, warnings)

    # Печать финального fb2 в файл 
    fb2_cfg = config.get("fb2") or {}
    print_mode = fb2_cfg.get("print-mode", "pretty")

    _write_fb2(tree, print_mode, fb2_path, warnings)


