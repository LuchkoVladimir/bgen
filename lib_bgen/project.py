"""Проект книги: конфигурация, файлы, статистика."""
from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from .common import BgenError, KNOWN_FORMATS


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

