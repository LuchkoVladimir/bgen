"""Проект книги: конфигурация, файлы, статистика."""
from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

try:
    import jsonschema
except ImportError:
    raise ImportError("Требуется jsonschema. Установите: pip install jsonschema")

from .common import BgenError, KNOWN_FORMATS, SCHEMAS_DIR, TYPOGRAPHY_FILE

CONFIG_SCHEMA_FILE = SCHEMAS_DIR / "config.schema.json"

PATHS_TYPOG = "typography"
PATHS_FB2_DESC = "fb2_description"
PATHS_DOCX_REF = "reference_doc"
PATHS_EPUB_CSS = "epub_css"
PATHS_EPUB_META_XML = "epub_metadata"

# ============================================================
# Конфигурация
# ============================================================

def _load_config(project_path: Path) -> dict:
    """Читает config.yaml проекта. Бросает BgenError, если файла нет."""
    config_path = project_path / "config.yaml"
    if not config_path.exists():
        raise BgenError(f"{config_path} не найден")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _validate_config(config: dict) -> None:
    """Валидация config.yaml по JSON Schema.

    Бросает BgenError с человекочитаемыми ошибками (путь к полю + сообщение).
    """
    if not CONFIG_SCHEMA_FILE.exists():
        raise BgenError(
            f"схема конфига не найдена: {CONFIG_SCHEMA_FILE}. "
            f"Проверьте дистрибутив bgen."
        )

    try:
        with open(CONFIG_SCHEMA_FILE, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise BgenError(
            f"не удалось загрузить схему конфига {CONFIG_SCHEMA_FILE}: {e}"
        )

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))

    if not errors:
        return

    lines = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        lines.append(f"  {path}: {err.message}")

    raise BgenError(
        "config.yaml не прошёл валидацию по схеме:\n" + "\n".join(lines)
    )


def _validate_project_path(project_path: Path) -> Path:
    """Проверяет, что путь — существующая директория. Возвращает resolve()."""
    project_path = project_path.resolve()
    if not project_path.is_dir():
        raise BgenError(f"{project_path} не директория")
    return project_path


def _resolve_formats(config: dict, only: str | None) -> list[str]:
    """Определяет список форматов для сборки.

    only — строка "fb2,epub" из CLI; переопределяет config.
    Иначе — секции config с enabled: true.
    """
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
# Файлы
# ============================================================

def _get_body_files(project_path: Path) -> list[Path]:
    """Возвращает отсортированные .md файлы из body/ (рекурсивно)."""
    body_dir = project_path / "body"
    if not body_dir.exists():
        raise BgenError(f"директория {body_dir} не найдена")
    files = sorted(body_dir.rglob("*.md"))
    if not files:
        raise BgenError(f"в {body_dir} не найдено .md файлов")
    return files


def _resolve_file_paths(project_path: Path, config: dict) -> dict[str, Path | None]:
    """Эффективные пути к «дополнительным файлам» проекта.

    Не проверяет существование — только выбирает путь (конфиг → bgen/schemas).
    Возвращает dict: имя → Path (или None, если файл не применим/не задан).

    Имена:
      typography         — typography.txt (config.yaml → bgen/schemas)
      fb2_description    — fb2_description.xml (только если задан description_file)
      reference_doc      — reference.docx (docx.reference_doc → bgen/schemas)
      epub_css           — epub.css (epub.css → bgen/schemas)
      epub_metadata      — epub-metadata.xml (только если задан metadata-file)
    """
    fb2_cfg = config.get("fb2") or {}
    docx_cfg = config.get("docx") or {}
    epub_cfg = config.get("epub") or {}

    paths: dict[str, Path | None] = {}

    # typography: config → bgen/schemas/typography.txt
    typo = config.get("typography", "")
    paths[PATHS_TYPOG] = (project_path / typo).resolve() if typo else TYPOGRAPHY_FILE

    # fb2_description: только если задан description-file
    desc_rel = fb2_cfg.get("description-file", "")
    paths[PATHS_FB2_DESC] = (project_path / desc_rel).resolve() if desc_rel else None

    # reference_doc: config → bgen/schemas/reference.docx
    ref = docx_cfg.get("reference_doc", "")
    paths[PATHS_DOCX_REF] = (project_path / ref).resolve() if ref else SCHEMAS_DIR / "reference.docx"

    # epub_css: config → bgen/schemas/epub.css
    css = epub_cfg.get("css", "")
    paths[PATHS_EPUB_CSS] = (project_path / css).resolve() if css else SCHEMAS_DIR / "epub.css"

    # epub_metadata: только если задан metadata-file
    meta_file = epub_cfg.get("metadata-file", "")
    paths[PATHS_EPUB_META_XML] = (project_path / meta_file).resolve() if meta_file else None

    return paths


def _check_file_paths(
    paths: dict[str, Path | None],
    warnings: list[str],
    strict: bool,
) -> None:
    """Проверяет существование файлов из _resolve_file_paths.

    strict=True  — BgenError на первый отсутствующий файл (для build).
    strict=False — warning на каждый отсутствующий файл (для check).
    """
    missing: list[str] = []
    for name, path in paths.items():
        if path is None:
            continue
        if not path.exists():
            missing.append(f"{name}: файл не найден: {path}")

    if strict:
        if missing:
            raise BgenError("\n".join(missing))
    else:
        warnings.extend(missing)


# ============================================================
# Статистика
# ============================================================

def _strip_markdown(text: str) -> str:
    """Грубо удаляет Markdown-разметку для статистики."""
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
    """Считает объёмные метрики по списку .md файлов."""
    full = "\n".join(_strip_markdown(p.read_text(encoding="utf-8")) for p in files)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*", full)
    return {
        "files": len(files),
        "chars_with_spaces": len(full),
        "chars_no_spaces": len(re.sub(r"\s", "", full)),
        "words": len(words),
    }


def stat(project_path: Path) -> dict | None:
    """Статистика текста проекта. Возвращает dict или None, если файлов нет."""
    project_path = _validate_project_path(project_path)
    files = _get_body_files(project_path)
    return _get_stat_from_md(files)

