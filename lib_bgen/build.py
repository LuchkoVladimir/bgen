"""Диспетчер сборки: выбирает формат и вызывает его сборщик.

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

import os
from pathlib import Path

from .common import BgenError
from .project import (
    _build_config,
    _resolve_formats,
    _validate_project_path,
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
    config = _build_config(project_path)

    formats = _resolve_formats(config, only)

    output_dir = project_path / config.get("output-dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["BGEN_TYPOGRAPHY"] = str(config.get("typography-file", ""))

    results: list[tuple[str, Path]] = []
    for fmt in formats:
        if fmt == "fb2":
            from .fb2.build import _build_fb2
            output_path = _build_fb2(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "docx":
            from .docx_build import _build_docx
            output_path = _build_docx(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "epub":
            from .epub_build import _build_epub
            output_path = _build_epub(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "txt":
            from .txt_build import _build_txt
            output_path = _build_txt(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results

