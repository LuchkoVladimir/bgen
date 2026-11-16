"""Диспетчер сборки: выбирает формат и вызывает его сборщик."""
from __future__ import annotations

import os
from pathlib import Path

from .common import BgenError
from .project import (
    _load_config,
    _resolve_formats,
    _validate_config,
    _validate_project_path,
    _resolve_file_paths,
    _check_file_paths,
    PATHS_TYPOG
)


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
    _validate_config(config)

    # Централизованная проверка «дополнительных файлов» (typography,
    # fb2_description, reference_doc, epub_css, epub_metadata).
    paths = _resolve_file_paths(project_path, config)
    _check_file_paths(paths, warnings, strict=True)

    formats = _resolve_formats(config, only)

    output_dir = project_path / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["BGEN_TYPOGRAPHY"] = str(paths[PATHS_TYPOG])

    results: list[tuple[str, Path]] = []
    for fmt in formats:
        if fmt == "fb2":
            from .fb2.build import _build_fb2
            output_path = _build_fb2(project_path, config, paths, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "docx":
            from .docx_build import _build_docx
            output_path = _build_docx(project_path, config, paths, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "epub":
            from .epub_build import _build_epub
            output_path = _build_epub(project_path, config, paths, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "txt":
            from .txt_build import _build_txt
            output_path = _build_txt(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results

