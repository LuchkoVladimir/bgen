#!/usr/bin/env python3
"""lib_bgen: библиотека bgen (конфигурация, структура, сборка, статистика)."""
from __future__ import annotations

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

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
BGEN_DIR = Path(__file__).resolve().parent

KNOWN_FORMATS = {"fb2"}


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

def read_annotation(project_path: Path) -> str | None:
    path = project_path / "_annotation.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)


def iter_text_files(project_path: Path) -> list[Path]:
    """Возвращает md-файлы из project_path/body/, отсортированные по пути."""
    body_dir = project_path / "body"
    if not body_dir.exists():
        raise BgenError(f"директория {body_dir} не найдена")
    files = sorted(body_dir.rglob("*.md"))
    if not files:
        raise BgenError(f"в {body_dir} не найдено .md файлов")
    return files


# ============================================================
# Предобработка Markdown: ::: {.class} -> маркеры
# ============================================================

# Захватываем строку с классами целиком: ".epigraph .book" и т.п.
_DIV_RE = re.compile(r"(?ms)^:::\s*\{\s*([^}]*)\s*\}\s*\n(.*?)^:::\s*$")


def _preprocess_md(files: list[Path]) -> tuple[str, dict[str, tuple[list[str], str]]]:
    """Склеивает файлы, заменяет ::: {.class .class} блоки на маркеры.

    Возвращает (склеенный_текст, маркеры), где маркеры — dict:
    marker_id -> (classes, content).
    classes — список классов без ведущей точки (["epigraph", "book"]).
    """
    parts = [f.read_text(encoding="utf-8") for f in files]
    text = "\n\n".join(parts)

    markers: dict[str, tuple[list[str], str]] = {}
    counter = [0]

    def replace(m: re.Match) -> str:
        counter[0] += 1
        marker_id = f"BGENMARKER{counter[0]:08d}ENDMARKER"
        classes = [
            c.lstrip(".").strip()
            for c in m.group(1).split()
            if c.strip()
        ]
        markers[marker_id] = (classes, m.group(2).strip())
        return f"\n\n{marker_id}\n\n"

    text = _DIV_RE.sub(replace, text)
    return text, markers


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


def _run_pandoc_fb2(md_file: Path, meta_path: Path, output: Path, resource_path: Path) -> list[str]:
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "fb2",
        "--standalone",
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
    ]
    abbrevs = BGEN_DIR / "abbrevs.txt"
    if abbrevs.exists():
        cmd.extend(["--abbreviations", str(abbrevs)])
    cmd.extend(["-o", str(output), str(md_file)])

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

def _build_epigraph(content: str) -> ET.Element:
    epigraph = ET.Element(f"{{{FB2_NS}}}epigraph")
    parts = re.split(r"\n\s*\n", content)
    author = None
    if len(parts) > 1 and parts[-1].strip().startswith("—"):
        author = parts[-1].strip().lstrip("—").strip()
        parts = parts[:-1]
    for para in parts:
        para = para.strip()
        if para:
            p = ET.SubElement(epigraph, f"{{{FB2_NS}}}p")
            p.text = para
    if author:
        ta = ET.SubElement(epigraph, f"{{{FB2_NS}}}text-author")
        ta.text = author
    return epigraph


def _build_poem(content: str) -> ET.Element:
    poem = ET.Element(f"{{{FB2_NS}}}poem")
    stanzas = re.split(r"\n\s*\n", content.strip())
    for stanza_text in stanzas:
        stanza_text = stanza_text.strip()
        if not stanza_text:
            continue
        stanza = ET.SubElement(poem, f"{{{FB2_NS}}}stanza")
        for line in stanza_text.split("\n"):
            line = line.strip()
            if line:
                v = ET.SubElement(stanza, f"{{{FB2_NS}}}v")
                v.text = line
    return poem


def _build_asterism() -> ET.Element:
    p = ET.Element(f"{{{FB2_NS}}}p")
    p.text = "* * *"
    return p


def _build_marker_replacement(classes: list[str], content: str, warnings: list[str]) -> ET.Element | None:
    # "epigraph" — основной класс, определяет тип элемента.
    # "book" — уточнение (эпиграф книги), обрабатывается в _postprocess_fb2.
    if "epigraph" in classes:
        return _build_epigraph(content)
    if "poem" in classes:
        return _build_poem(content)
    if "asterism" in classes:
        return _build_asterism()
    warnings.append(f"неизвестный класс маркера: {' '.join(classes)}")
    return None


def _replace_markers(
    root: ET.Element,
    markers: dict[str, tuple[list[str], str]],
    warnings: list[str],
) -> None:
    for parent in list(root.iter()):
        i = 0
        while i < len(parent):
            child = parent[i]
            if child.tag == f"{{{FB2_NS}}}p":
                text = (child.text or "").strip()
                if text in markers:
                    classes, content = markers[text]
                    replacement = _build_marker_replacement(classes, content, warnings)
                    if replacement is not None:
                        # Помечаем эпиграф книги атрибутом, чтобы потом
                        # отличить его от эпиграфа главы.
                        if replacement.tag == f"{{{FB2_NS}}}epigraph" and "book" in classes:
                            replacement.set("_bgen_book", "1")
                        parent.remove(child)
                        parent.insert(i, replacement)
                        i += 1
                        continue
            i += 1


def _move_book_epigraph_to_body(root: ET.Element, warnings: list[str]) -> None:
    """Перемещает <epigraph _bgen_book="1"> из безымянной секции в <body>.

    Pandoc оборачивает эпиграф книги в <section> без <title>.
    По схеме FB2 эпиграф книги должен быть прямым потомком <body>.
    """
    ns = {"fb": FB2_NS}
    body = root.find("fb:body", ns)
    if body is None:
        return

    for section in list(body.findall("fb:section", ns)):
        # Ищем эпиграф, помеченный как книжный
        book_ep = None
        for ep in section.findall("fb:epigraph", ns):
            if ep.get("_bgen_book") == "1":
                book_ep = ep
                break
        if book_ep is None:
            continue

        # Если в секции только этот эпиграф (и, возможно, empty-line) —
        # секция бессмысленна, эпиграф выносим, секцию удаляем.
        meaningful = [
            c for c in section
            if not (c.tag == f"{{{FB2_NS}}}epigraph" and c is book_ep)
            and c.tag != f"{{{FB2_NS}}}empty-line"
        ]
        if meaningful:
            warnings.append(
                "эпиграф книги оказался внутри секции с содержимым; "
                "перемещён в <body>, но проверьте структуру"
            )

        # Убираем временный атрибут
        book_ep.attrib.pop("_bgen_book", None)

        # Вставляем эпиграф в body на место секции
        idx = list(body).index(section)
        section.remove(book_ep)
        body.insert(idx, book_ep)

        # Если секция опустела — удаляем
        if len(section) == 0:
            body.remove(section)


def _postprocess_fb2(
    fb2_path: Path,
    config: dict,
    annotation_text: str | None,
    markers: dict[str, tuple[str, str]],
) -> list[str]:
    # Регистрируем FB2 namespace как default (без префикса ns0).
    # Это глобальная настройка ElementTree, влияет на все последующие write().
    ET.register_namespace("", FB2_NS)

    tree = ET.parse(fb2_path)
    root = tree.getroot()
    ns = {"fb": FB2_NS}

    title_info = root.find(".//fb:title-info", ns)
    if title_info is None:
        raise BgenError("title-info не найден в сгенерированном FB2")

    fb2_cfg = config.get("fb2") or {}
    warnings: list[str] = []

    # Маркеры (:epigraph, :poem, :asterism)
    _replace_markers(root, markers, warnings)
    # Эпиграф книги: вынести из безымянной секции в <body>
    _move_book_epigraph_to_body(root, warnings)
    # Pandoc FB2-writer добавляет пустой <p><emphasis /></p> после таблиц.
    for p in list(root.iter(f"{{{FB2_NS}}}p")):
        emph = p.find(f"{{{FB2_NS}}}emphasis")
        if emph is not None and not (emph.text or "").strip() and len(emph) == 0:
            if not (p.text or "").strip() and len(p) == 1:
                for parent in root.iter():
                    if p in list(parent):
                        parent.remove(p)
                        break

    # Жанры
    for g in title_info.findall("fb:genre", ns):
        title_info.remove(g)
    for g in fb2_cfg.get("genres") or ["unrecognised"]:
        ET.SubElement(title_info, f"{{{FB2_NS}}}genre").text = g

    # Аннотация
    for old in title_info.findall("fb:annotation", ns):
        title_info.remove(old)
    if annotation_text:
        ann = ET.SubElement(title_info, f"{{{FB2_NS}}}annotation")
        for para in re.split(r"\n\s*\n", annotation_text):
            para = para.strip()
            if para:
                ET.SubElement(ann, f"{{{FB2_NS}}}p").text = para

    # document-info
    description = root.find(".//fb:description", ns)
    if description is None:
        description = ET.SubElement(root, f"{{{FB2_NS}}}description")
    doc_info = description.find("fb:document-info", ns)
    if doc_info is None:
        doc_info = ET.SubElement(description, f"{{{FB2_NS}}}document-info")

    if doc_info.find("fb:id", ns) is None:
        ET.SubElement(doc_info, f"{{{FB2_NS}}}id").text = "bgen-generated"
    if doc_info.find("fb:version", ns) is None:
        ET.SubElement(doc_info, f"{{{FB2_NS}}}version").text = "1.0"

    date_val = fb2_cfg.get("date") or date_cls.today().isoformat()
    for old in doc_info.findall("fb:date", ns):
        doc_info.remove(old)
    ET.SubElement(doc_info, f"{{{FB2_NS}}}date", {"value": date_val}).text = date_val

    # Косметика
    if fb2_cfg.get("pretty_print", False):
        try:
            ET.indent(tree, space="  ", level=0)
        except AttributeError:
            warnings.append("ET.indent недоступен (Python < 3.9), форматирование пропущено")

    tree.write(fb2_path, encoding="utf-8", xml_declaration=True)
    return warnings


def _build_one_fb2(
    project_path: Path,
    config: dict,
    annotation_text: str | None,
    output_dir: Path,
) -> tuple[Path, list[str]]:
    fb2_cfg = config.get("fb2") or {}
    output_name = fb2_cfg.get("output_name", "book.fb2")
    output_path = output_dir / output_name

    md_files = iter_text_files(project_path)
    concatenated, markers = _preprocess_md(md_files)

    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        md_path = tmpdir / "book.md"
        md_path.write_text(concatenated, encoding="utf-8")
        meta_path, meta_warnings = _build_fb2_metadata(project_path, config, tmpdir)
        warnings.extend(meta_warnings)
        warnings.extend(_run_pandoc_fb2(md_path, meta_path, output_path, project_path))

    warnings.extend(_postprocess_fb2(output_path, config, annotation_text, markers))
    return output_path, warnings


# ============================================================
# Высокоуровневые команды
# ============================================================

def build(project_path: Path, only: str | None = None) -> list[tuple[str, Path, list[str]]]:
    project_path = _validate_project_path(project_path)
    config = load_config(project_path)

    formats = _resolve_formats(config, only)
    if not formats:
        raise BgenError("не включено ни одного формата (проверьте config.yaml)")

    output_dir = project_path / config.get("output_dir", "build")
    output_dir.mkdir(exist_ok=True)
    annotation_text = read_annotation(project_path)

    results: list[tuple[str, Path, list[str]]] = []
    for fmt in formats:
        if fmt == "fb2":
            output_path, warnings = _build_one_fb2(
                project_path, config, annotation_text, output_dir
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
    load_config(project_path)  # проверяем, что config.yaml есть
    files = iter_text_files(project_path)
    return _analyze(files)


