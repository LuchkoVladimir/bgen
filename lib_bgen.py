#!/usr/bin/env python3
"""lib_bgen: библиотека bgen (конфигурация, структура, сборка, статистика)."""
from __future__ import annotations

import copy
import re
import subprocess
import tempfile
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
_DOC_INFO_ORDER = ["author", "program-used", "date", "id", "version"]


class BgenError(Exception):
    """Ошибка bgen, пригодная для показа пользователю."""


# ============================================================
# Конфигурация
# ============================================================

def load_config(project_path: Path) -> dict:
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
    return formats


# ============================================================
# Структура проекта
# ============================================================

def iter_text_files(project_path: Path) -> list[Path]:
    body_dir = project_path / "body"
    if not body_dir.exists():
        raise BgenError(f"директория {body_dir} не найдена")
    files = sorted(body_dir.rglob("*.md"))
    if not files:
        raise BgenError(f"в {body_dir} не найдено .md файлов")
    return files


# ============================================================
# Сборка FB2
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

    meta.pop("genre", None)
    meta.pop("genres", None)

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

def _remove_empty_emphasis(root: ET.Element) -> None:
    """Известный баг Pandoc FB2-writer: после таблиц добавляется <p><emphasis /></p>."""
    ns = FB2_NS
    for p in list(root.iter(f"{{{ns}}}p")):
        emph = p.find(f"{{{ns}}}emphasis")
        if emph is not None and not (emph.text or "").strip() and len(emph) == 0:
            if not (p.text or "").strip() and len(p) == 1:
                for parent in root.iter():
                    if p in list(parent):
                        parent.remove(p)
                        break


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


def _fix_book_level_elements(root: ET.Element) -> None:
    """За один проход по <body>: переносит <annotation> и <epigraph>
    из безымянных секций в <title-info> и <body> соответственно.

    Безымянная секция (без <title>) — признак элемента книжного уровня:
    Pandoc оборачивает эпиграф/аннотацию книги, стоящие до первого заголовка,
    в <section> без <title>. Если секция с <title> — это эпиграф/аннотация
    главы, их не трогаем (схема FB2 это разрешает).
    """
    ns = {"fb": FB2_NS}
    body = root.find("fb:body", ns)
    if body is None:
        return
    title_info = root.find(".//fb:title-info", ns)
    if title_info is None:
        return

    # Собираем аннотацию книги из <annotation> в безымянных секциях.
    book_annotation_children = None

    for section in list(body.findall("fb:section", ns)):
        # Секция с <title> — это глава, не трогаем.
        if section.find("fb:title", ns) is not None:
            continue

        # Аннотация книги
        annotation_el = section.find("fb:annotation", ns)
        if annotation_el is not None:
            if book_annotation_children is None:
                book_annotation_children = list(annotation_el)
            else:
                book_annotation_children.extend(list(annotation_el))
            section.remove(annotation_el)

        # Эпиграф книги (может быть несколько)
        for epigraph_el in list(section.findall("fb:epigraph", ns)):
            idx = list(body).index(section)
            section.remove(epigraph_el)
            body.insert(idx, epigraph_el)

        # Если секция опустела — удаляем
        if len(section) == 0:
            body.remove(section)

    # Вставляем аннотацию книги в <title-info>
    if book_annotation_children is not None:
        for old in title_info.findall("fb:annotation", ns):
            title_info.remove(old)
        ann = ET.SubElement(title_info, f"{{{FB2_NS}}}annotation")
        for child in book_annotation_children:
            ann.append(child)


def _postprocess_fb2(
    fb2_path: Path,
    config: dict,
) -> list[str]:
    ET.register_namespace("", FB2_NS)

    tree = ET.parse(fb2_path)
    root = tree.getroot()
    ns = {"fb": FB2_NS}

    title_info = root.find(".//fb:title-info", ns)
    if title_info is None:
        raise BgenError("title-info не найден в сгенерированном FB2")

    fb2_cfg = config.get("fb2") or {}
    warnings: list[str] = []

    # Известный баг Pandoc: пустой <emphasis /> после таблиц.
    _remove_empty_emphasis(root)

    # Известный баг Pandoc: оборачивание эпиграфа/аннотации книги в <section>
    _fix_book_level_elements(root)

    # Жанры
    for g in title_info.findall("fb:genre", ns):
        title_info.remove(g)
    for g in fb2_cfg.get("genres") or ["unrecognised"]:
        ET.SubElement(title_info, f"{{{FB2_NS}}}genre").text = g

    # document-info
    description = root.find(".//fb:description", ns)
    if description is None:
        description = ET.SubElement(root, f"{{{FB2_NS}}}description")
    doc_info = description.find("fb:document-info", ns)
    if doc_info is None:
        doc_info = ET.SubElement(description, f"{{{FB2_NS}}}document-info")

    # document-info требует <author>. Копируем из title-info, если своего нет.
    if doc_info.find("fb:author", ns) is None:
        title_author = title_info.find("fb:author", ns)
        if title_author is not None:
            doc_info.insert(0, copy.deepcopy(title_author))

    if doc_info.find("fb:id", ns) is None:
        ET.SubElement(doc_info, f"{{{FB2_NS}}}id").text = "bgen-generated"
    if doc_info.find("fb:version", ns) is None:
        ET.SubElement(doc_info, f"{{{FB2_NS}}}version").text = "1.0"

    date_val = fb2_cfg.get("date") or date_cls.today().isoformat()
    for old in doc_info.findall("fb:date", ns):
        doc_info.remove(old)
    ET.SubElement(doc_info, f"{{{FB2_NS}}}date", {"value": date_val}).text = date_val

    # Pandoc генерирует xlink:type="inlineImageType"/"imageType",
    # схема FB2 требует fixed value "simple".
    XLINK_NS = "http://www.w3.org/1999/xlink"
    for el in root.iter():
        xlink_type = el.get(f"{{{XLINK_NS}}}type")
        if xlink_type is not None and xlink_type != "simple":
            el.set(f"{{{XLINK_NS}}}type", "simple")

    # Приводим порядок в соответствие со схемой FB2 (после всех вставок)
    _sort_children_by_order(title_info, _TITLE_INFO_ORDER)
    _sort_children_by_order(doc_info, _DOC_INFO_ORDER)

    # Косметика
    if fb2_cfg.get("pretty_print", False):
        try:
            ET.indent(tree, space="  ", level=0)
        except AttributeError:
            warnings.append("ET.indent недоступен (Python < 3.9), форматирование пропущено")

    tree.write(fb2_path, encoding="utf-8", xml_declaration=True)
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
# Высокоуровневые команды
# ============================================================

def _build_one_fb2(
    project_path: Path,
    config: dict,
    output_dir: Path,
) -> tuple[Path, list[str]]:
    fb2_cfg = config.get("fb2") or {}
    output_name = fb2_cfg.get("output_name", "book.fb2")
    output_path = output_dir / output_name

    md_files = iter_text_files(project_path)

    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, meta_warnings = _build_fb2_metadata(project_path, config, tmpdir)
        warnings.extend(meta_warnings)
        warnings.extend(_run_pandoc_fb2(md_files, meta_path, output_path, project_path))

    warnings.extend(_postprocess_fb2(output_path, config))

    xsd_errors = _validate_fb2(output_path)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    return output_path, warnings


def build(project_path: Path, only: str | None = None) -> list[tuple[str, Path, list[str]]]:
    project_path = _validate_project_path(project_path)
    config = load_config(project_path)

    formats = _resolve_formats(config, only)
    if not formats:
        raise BgenError("не включено ни одного формата (проверьте config.yaml)")

    output_dir = project_path / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, Path, list[str]]] = []
    for fmt in formats:
        if fmt == "fb2":
            output_path, warnings = _build_one_fb2(
                project_path, config, output_dir
            )
            results.append((fmt, output_path, warnings))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results


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
    return text


def _analyze(files: list[Path]) -> dict:
    full = "\n".join(_strip_markdown(p.read_text(encoding="utf-8")) for p in files)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*", full)
    counter = Counter(w.lower() for w in words)
    return {
        "files": len(files),
        "chars_with_spaces": len(full),
        "chars_no_spaces": len(re.sub(r"\s", "", full)),
        "words": len(words),
        "unique_words": len(counter),
        "top": counter.most_common(20),
    }


def stat(project_path: Path) -> dict | None:
    project_path = _validate_project_path(project_path)
    load_config(project_path)
    files = iter_text_files(project_path)
    return _analyze(files)


