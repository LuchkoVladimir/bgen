#!/usr/bin/env python3
"""lib_bgen: библиотека bgen (конфигурация, структура, сборка, статистика)."""
from __future__ import annotations

import copy
import re
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date as date_cls
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

try:
    from lxml import etree as lxml_etree
except ImportError:
    raise ImportError("Требуется lxml. Установите: pip install lxml")

PROGRAM_USED = "bgen-1.0"

XML_NS = "http://www.w3.org/XML/1998/namespace"
FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
BGEN_DIR = Path(__file__).resolve().parent
SCHEMAS_DIR = BGEN_DIR / "schemas"
FB2_XSD = SCHEMAS_DIR / "FictionBook.xsd"

KNOWN_FORMATS = {"fb2"}

# Порядок элементов по схеме FB2 (TitleInfo, DocumentInfo).
_TITLE_INFO_ORDER = [
    "genre", "author", "book-title", "annotation", "keywords",
    "date", "coverpage", "lang", "src-lang", "translator", "sequence",
]
_DOC_INFO_ORDER = ["author", "program-used", "date", "src-url", "src-ocr", "id", "version", "history", "publisher"]

class BgenError(Exception):
    """Ошибка bgen, пригодная для показа пользователю."""


# ============================================================
# Конфигурация
# ============================================================

def _load_config(project_path: Path) -> dict:
    config_path = project_path / "config.yaml"
    if not config_path.exists():
        raise BgenError(f"{config_path} не найден")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _validate_project_path(project_path: Path) -> Path:
    project_path = project_path.resolve()
    if not project_path.is_dir():
        raise BgenError(f"{project_path} не директория")
    return project_path


def _resolve_formats(config: dict, only: str | None) -> list[str]:
    if only:
        formats = [f.strip() for f in only.split(",") if f.strip()]
        unknown = [f for f in formats if f not in KNOWN_FORMATS]
        if unknown:
            raise BgenError(f"неизвестный формат: {', '.join(unknown)}")
        return formats

    formats = []
    for fmt in KNOWN_FORMATS:
        section = config.get(fmt) or {}
        if section.get("enabled", False):
            formats.append(fmt)

    if not formats:
        raise BgenError("не включено ни одного формата (проверьте config.yaml)")

    return formats


# ============================================================
# Структура проекта
# ============================================================

def _get_body_files(project_path: Path) -> list[Path]:
    body_dir = project_path / "body"
    if not body_dir.exists():
        raise BgenError(f"директория {body_dir} не найдена")
    files = sorted(body_dir.rglob("*.md"))
    if not files:
        raise BgenError(f"в {body_dir} не найдено .md файлов")
    return files


# ============================================================
# Статистика
# ============================================================

def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"^:::\s*\{[^}]*\}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^:::\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", text)  # Span
    return text


def _get_stat_from_md(files: list[Path]) -> dict:
    full = "\n".join(_strip_markdown(p.read_text(encoding="utf-8")) for p in files)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*", full)
    words4 = re.findall(r"[A-Za-zА-Яа-яЁё]{4,}(?:-[A-Za-zА-Яа-яЁё]{4,})*", full)
    counter = Counter(w.lower() for w in words)
    counter4 = Counter(w.lower() for w in words4)
    return {
        "files": len(files),
        "chars_with_spaces": len(full),
        "chars_no_spaces": len(re.sub(r"\s", "", full)),
        "words": len(words),
        "unique_words": len(counter),
        "top": counter4.most_common(20),
        "filenames": files,
    }


# ============================================================
# FB2-специфичное
# ============================================================

def _build_fb2_metadata(project_path: Path, config: dict, tmpdir: Path) -> tuple[Path, list[str]]:
    warnings: list[str] = []
    meta = dict(config.get("metadata") or {})
    meta.setdefault("lang", "ru")

    if not meta.get("title"):
        raise BgenError("metadata.title не задан в config.yaml")
    if not meta.get("author"):
        raise BgenError("metadata.author не задан в config.yaml")

    cover = meta.get("cover-image")
    if cover:
        cover_path = (project_path / cover).resolve()
        if cover_path.exists():
            meta["cover-image"] = str(cover_path)
        else:
            warnings.append(f"обложка не найдена, пропускаем: {cover_path}")
            meta.pop("cover-image")

    meta_path = tmpdir / "metadata.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)
    return meta_path, warnings


def _run_pandoc_fb2(md_files: list[Path], meta_path: Path, output: Path,
                    resource_path: Path) -> list[str]:
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "fb2",
        "--standalone",
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
    ]
    filter_path = BGEN_DIR / "filter_bgen.lua"
    if filter_path.exists():
        cmd.extend(["--lua-filter", str(filter_path)])
    abbrevs = BGEN_DIR / "abbrevs.txt"
    if abbrevs.exists():
        cmd.extend(["--abbreviations", str(abbrevs)])
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    warnings: list[str] = []
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")
    return warnings


# ============================================================
# Постобработка FB2
# ============================================================

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


def _update_book_anno_and_epi_from_body(body: ET.Element, title_info: ET.Element) -> None:
    """За один проход по <body>: переносит <annotation> и <epigraph>
    из безымянных секций в <title-info> и <body> соответственно.

    Безымянная секция (без <title>) — признак элемента книжного уровня:
    Pandoc оборачивает эпиграф/аннотацию книги, стоящие до первого заголовка,
    в <section> без <title>. Если секция с <title> — это эпиграф/аннотация
    главы, их не трогаем (схема FB2 это разрешает).
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

    # Собираем аннотацию и эпиграфы книги в безымянной секции
    book_annotations = []
    book_epigraphs = []

    if blank_sections:
        section = blank_sections[0]
        book_annotations = list(section.findall("fb:annotation", ns))
        for ann in book_annotations:
            section.remove(ann)
        book_epigraphs = list(section.findall("fb:epigraph", ns))
        for ep in book_epigraphs:
            section.remove(ep)
        leftover = [c for c in section]
        if leftover:
            raise BgenError(
                f"в безымянной секции после переноса annotation/epigraph "
                f"осталось содержимое: {[c.tag for c in leftover]}"
            )
        body.remove(section)

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
    project_path: Path,
    config: dict,
    generated_title_info: ET.Element,
    generated_doc_info: ET.Element,
) -> list[str]:
    """Применяет fb2_description.xml в режиме template или override.

    auto     — ничего не делает.
    template — обходит ШАБЛОН; для каждого элемента, который есть и в шаблоне,
               и в сгенерированном description, заменяет содержимое шаблона
               на сгенерированное. Новых элементов не добавляет.
               Служебные поля Pandoc (см. _PANDOC_OPTIONAL_TAGS) уже удалены
               из сгенерированного description до вызова.
    override — заменяет <description> целиком на содержимое файла.
    """
    fb2_cfg = config.get("fb2") or {}
    mode = fb2_cfg.get("description", "auto")
    if mode == "auto":
        return []

    if mode not in ("template", "override"):
        raise BgenError(f"неизвестный режим fb2.description: {mode}")

    desc_path = project_path / "fb2_description.xml"
    if not desc_path.exists():
        raise BgenError(
            f"fb2.description: {mode}, но файл не найден: {desc_path}"
        )

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

    warnings: list[str] = []

    if mode == "override":
        old_desc = root.find(f"{{{FB2_NS}}}description")
        if old_desc is not None:
            idx = list(root).index(old_desc)
            root.remove(old_desc)
            root.insert(idx, custom_root)
        else:
            root.insert(0, custom_root)
        warnings.append(
            "fb2.description=override: значения config.yaml для description "
            "(author, book-title, genre, date, annotation, coverpage, lang) "
            "игнорируются"
        )
        return warnings

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

    return warnings


def _fix_fb2_pandoc_bugs(root: ET.Element) -> None:
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


def _write_fb2(tree: ET.ElementTree, print_pretty: bool, fb2_path: Path) -> list[str]:
    """Иерархическое форматирование XML (ET.indent) и запись файла.

    Возвращает список предупреждений (например, если ET.indent недоступен
    на Python < 3.9). Запись выполняется всегда, даже если форматирование
    пропущено.
    """
    warnings: list[str] = []

    if print_pretty:
        try:
            ET.indent(tree, space="  ", level=0)
        except AttributeError:
            warnings.append("ET.indent недоступен (Python < 3.9), форматирование пропущено")

    tree.write(fb2_path, encoding="utf-8", xml_declaration=True)
    return warnings


def _update_metadata(config: dict, title_info: ET.Element, doc_info: ET.Element) -> None:
    fb2_cfg = config.get("fb2") or {}
    ns = {"fb": FB2_NS}

    # Жанры
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
            match = g.get("match")
            if match is not None:
                genre_el.set("match", str(match))
        elif isinstance(g, str):
            ET.SubElement(title_info, f"{{{FB2_NS}}}genre").text = g
        else:
            raise BgenError(f"fb2.genres: ожидается строка или словарь, получено {type(g).__name__}")

    # title-info/keywords (список строк через запятую)
    keywords = fb2_cfg.get("keywords") or []
    if keywords:
        for old in title_info.findall("fb:keywords", ns):
            title_info.remove(old)
        kw_el = ET.SubElement(title_info, f"{{{FB2_NS}}}keywords")
        kw_el.text = ", ".join(str(k) for k in keywords)

    # title-info/date
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

    # title-info/sequence (может быть несколько)
    sequences = fb2_cfg.get("sequence") or []
    for seq in sequences:
        if isinstance(seq, str):
            if not seq:
                continue  # пустая строка — пропускаем
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


    # document-info/author: копируем первого автора из title-info, если включено.
    copy_author = fb2_cfg.get("doc-author-copy-first-from-title", False)
    if copy_author:
        first_title_author = title_info.find("fb:author", ns)  # find вернёт первый
        if first_title_author is not None:
            doc_info.append(copy.deepcopy(first_title_author))

    # document-info требует <author>. Копируем из title-info, если своего нет.
    if doc_info.find("fb:author", ns) is None:
        title_author = title_info.find("fb:author", ns)
        if title_author is not None:
            doc_info.append(copy.deepcopy(title_author))

    # document-info program-used pandoc генерирует свой, но мы пишем себя, так как включаем постобработку
    program_el = doc_info.find("fb:program-used", ns)
    if program_el is None:
        program_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}program-used")
    program_el.text = PROGRAM_USED

    # document-info нужен id
    book_id = _make_book_id(config)
    id_el = doc_info.find("fb:id", ns)
    if id_el is None:
        id_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}id")
    id_el.text = book_id

    # document-info version обязательна
    version_val = fb2_cfg.get("version") or "1.0"
    version_el = doc_info.find("fb:version", ns)
    if version_el is None:
        version_el = ET.SubElement(doc_info, f"{{{FB2_NS}}}version")
    version_el.text = str(version_val)

    # Дата TODO: разобраться, почему не отображается в fbreader
    date_val = fb2_cfg.get("date") or date_cls.today().isoformat()
    for old in doc_info.findall("fb:date", ns):
        doc_info.remove(old)
    ET.SubElement(doc_info, f"{{{FB2_NS}}}date", {"value": date_val}).text = date_val


def _postprocess_fb2(
    fb2_path: Path,
    config: dict,
    project_path: Path,
) -> list[str]:
    ET.register_namespace("", FB2_NS)

    tree = ET.parse(fb2_path)
    root = tree.getroot()
    ns = {"fb": FB2_NS}

    # Проверяем нужные нам для работы элементы структуры fb2 и получаем их из дерева
    title_info, doc_info, body = _check_fb2_affecting_sections(root)

    # Фикс известных багов
    _fix_fb2_pandoc_bugs(root)

    # В bgen мы пишем аннотацию и эпиграф перед первой секцией, чтобы pandoc обработал md. Теперь нужно
    # достать из созданной pandoc`ом для них секции и разместить где нужно
    _update_book_anno_and_epi_from_body(body, title_info)

    # Заполняем метадату по конфиге
    _update_metadata(config, title_info, doc_info)

    # Приводим порядок в соответствие со схемой FB2
    _sort_children_by_order(title_info, _TITLE_INFO_ORDER)

    # Приводим порядок в соответствие со схемой FB2
    _sort_children_by_order(doc_info, _DOC_INFO_ORDER)

    warnings: list[str] = []

    # fb2_description.xml (template / override)
    warnings.extend(_apply_custom_description(
        root, project_path, config, title_info, doc_info
    ))

    # Печать финального fb2 в файл 
    fb2_cfg = config.get("fb2") or {}
    print_pretty = fb2_cfg.get("pretty_print", False)

    warnings.extend(_write_fb2(tree, print_pretty, fb2_path))

    return warnings


# ============================================================
# Валидация FB2 по XSD
# ============================================================

def _validate_fb2(fb2_path: Path) -> list[str]:
    """Валидация FB2 по XSD. Возвращает список сообщений об ошибках.

    Если XSD-файл не найден — BgenError: без схемы валидация бессмысленна.
    """
    if not FB2_XSD.exists():
        raise BgenError(
            f"XSD-схема FB2 не найдена: {FB2_XSD}. "
            f"Положите FictionBook.xsd и связанные схемы в {SCHEMAS_DIR}"
        )

    try:
        schema_doc = lxml_etree.parse(str(FB2_XSD))
        schema = lxml_etree.XMLSchema(schema_doc)
    except lxml_etree.XMLSchemaParseError as e:
        raise BgenError(f"не удалось загрузить XSD-схему {FB2_XSD}: {e}")

    try:
        doc = lxml_etree.parse(str(fb2_path))
    except lxml_etree.XMLSyntaxError as e:
        return [f"FB2 не является well-formed XML: {e}"]

    if schema.validate(doc):
        return []

    errors = []
    for err in schema.error_log:
        errors.append(f"XSD: строка {err.line}, столбец {err.column}: {err.message}")
    return errors


# ============================================================
# Сборка FB2
# ============================================================

def _build_fb2(
    project_path: Path,
    config: dict,
    output_dir: Path,
) -> tuple[Path, list[str]]:
    fb2_cfg = config.get("fb2") or {}
    output_name = fb2_cfg.get("output_name", "book.fb2")
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, meta_warnings = _build_fb2_metadata(project_path, config, tmpdir)
        warnings.extend(meta_warnings)
        warnings.extend(_run_pandoc_fb2(md_files, meta_path, output_path, project_path))

    # pandoc формирует fb2 со множеством проблем, поэтому требуется постобработка
    warnings.extend(_postprocess_fb2(output_path, config, project_path))

    xsd_errors = _validate_fb2(output_path)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    return output_path, warnings


# ============================================================
# Высокоуровневые команды
# ============================================================

def stat(project_path: Path) -> dict | None:
    project_path = _validate_project_path(project_path)
    files = _get_body_files(project_path)
    return _get_stat_from_md(files)


def build(project_path: Path, only: str | None = None) -> list[tuple[str, Path, list[str]]]:
    project_path = _validate_project_path(project_path)
    config = _load_config(project_path)

    formats = _resolve_formats(config, only)

    output_dir = project_path / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, Path, list[str]]] = []
    for fmt in formats:
        if fmt == "fb2":
            output_path, warnings = _build_fb2(
                project_path, config, output_dir
            )
            results.append((fmt, output_path, warnings))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results


