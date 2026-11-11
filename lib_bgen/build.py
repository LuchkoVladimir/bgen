"""Диспетчер сборки: выбирает формат и вызывает его сборщик."""
from __future__ import annotations

from pathlib import Path

from .common import BgenError
from .project import _load_config, _resolve_formats, _validate_project_path


def build(
        project_path: Path,
        only: str | None = None,
        warnings: list[str] | None = None,
) -> list[tuple[str, Path]]:
    """Собирает книгу в форматах из config.yaml (или из only).

    warnings — внешний список: все предупреждения (включая накопленные
    до BgenError) пишутся в него. Если None — создаётся локальный.
    Возвращает список (формат, путь к файлу).
    """
    if warnings is None:
        warnings = []

    project_path = _validate_project_path(project_path)
    config = _load_config(project_path)

    formats = _resolve_formats(config, only)

    output_dir = project_path / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, Path]] = []
    for fmt in formats:
        if fmt == "fb2":
            from .fb2.build import _build_fb2
            output_path = _build_fb2(project_path, config, output_dir, warnings)
            results.append((fmt, output_path))
        elif fmt == "docx":
            from .docx.build import _build_docx
            output_path = _build_docx(project_path, config, output_dir, warnings)
            results.append((fmt, output_path))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results

