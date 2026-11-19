"""Проект книги: конфигурация, файлы, статистика.

Copyright (C) 2026 Владимир Лучко
This program is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.
This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with this program.
If not, see https://www.gnu.org/licenses/.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

try:
    import jsonschema
    from jsonschema import validators
except ImportError:
    raise ImportError("Требуется jsonschema. Установите: pip install jsonschema")

from .common import BgenError, KNOWN_FORMATS, SCHEMAS_DIR, TYPOGRAPHY_FILE

CONFIG_SCHEMA_FILE = SCHEMAS_DIR / "config.schema.json"

# ============================================================
# Конфигурация
# ============================================================
def _resolve_file_paths(project_path: Path, config: dict) -> dict:
    """Эффективные пути к «дополнительным файлам» проекта.

    Не проверяет существование — только выбирает путь (конфиг → bgen/schemas).
    Возвращает модифицированный путями конфиг.
    """
    fb2_cfg = config.get("fb2")
    docx_cfg = config.get("docx")
    epub_cfg = config.get("epub")

    missing: list[str] = []

    # config → bgen/schemas/typography.txt
    file = config.get("typography-file")
    file_path = (project_path / file).resolve() if file else TYPOGRAPHY_FILE
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        config["typography-file"] = str(file_path)

    # config → bgen/schemas/reference.docx
    file = docx_cfg.get("reference-file")
    file_path = (project_path / file).resolve() if file else SCHEMAS_DIR / "reference.docx"
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        docx_cfg["reference-file"] = str(file_path)

    # config → bgen/schemas/epub.css
    file = epub_cfg.get("css-file")
    file_path = (project_path / file).resolve() if file else SCHEMAS_DIR / "epub.css"
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        epub_cfg["css-file"] = str(file_path)

    # Тут нет дефолтных файлов в репозитории, поэтому файлы могут и отсутствовать и тогда не подменяются

    # только если задан description-file
    file = fb2_cfg.get("description-file")
    file_path = (project_path / file).resolve() if file else None
    if file_path and not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    elif file_path:
        fb2_cfg["description-file"] = str(file_path)

    # только если задан add-meta-xml-file
    file = epub_cfg.get("add-meta-xml-file")
    file_path = (project_path / file).resolve() if file else None
    if file_path and not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    elif file_path:
        epub_cfg["add-meta-xml-file"] = str(file_path)

    if missing:
        raise BgenError("\n".join(missing))

    return config


def _extend_with_default(validator_class):
    """Расширяет валидатор jsonschema: перед проверкой properties
    подставляет default из схемы для отсутствующих ключей.

    Внимание: работает только внутри уже существующих объектов
    (для секций нужен default: {}, для массивов - []).
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for prop, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(prop, copy.deepcopy(subschema["default"]))
        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return validators.extend(validator_class, {"properties": set_defaults})


DefaultValidatingValidator = _extend_with_default(jsonschema.Draft202012Validator)


def _build_config(project_path: Path) -> dict:
    """Читает config.yaml, валидирует по схеме и заполняет дефолтами.

    Возвращает полную валидную конфигу (или бросает BgenError).
    Дефолты берутся из config.schema.json (ключ default).
    """
    config_path = project_path / "config.yaml"
    if not config_path.exists():
        raise BgenError(f"{config_path} не найден")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

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

    validator = DefaultValidatingValidator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))

    if errors:
        lines = []
        for err in errors:
            path = ".".join(str(p) for p in err.absolute_path) or "(root)"
            lines.append(f"  {path}: {err.message}")
        raise BgenError(
            "config.yaml не прошёл валидацию по схеме:\n" + "\n".join(lines)
        )

    config = _resolve_file_paths(project_path, config)

    return config


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
        section = config.get(fmt)
        if section.get("enabled"):
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


def stat(project_path: Path) -> tuple[dict | None, str]:
    """Статистика текста проекта. Возвращает dict или None, если файлов нет."""
    project_path = _validate_project_path(project_path)
    files = _get_body_files(project_path)
    config = _build_config(project_path)
    return _get_stat_from_md(files), yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)


