"""DOCX: сборка одного формата (pandoc → build).

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

import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from .common import FILTER_FILE, BgenError


def _build_docx_metadata(project_path: Path, config: dict, tmpdir: Path, warnings: list[str]) -> Path:
    """Готовит metadata.yaml для Pandoc (DOCX).

    DOCX не использует coverpage, поэтому cover-image не передаётся.
    Возвращает путь к metadata.yaml.
    """
    meta = dict(config.get("metadata"))
    meta.setdefault("lang", "ru")

    # cover-image не нужен для DOCX
    meta.pop("cover-image", None)

    meta_path = tmpdir / "metadata.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)
    return meta_path


def _run_pandoc_docx(
    md_files: list[Path],
    meta_path: Path,
    output: Path,
    resource_path: Path,
    config: dict,
    env: dict,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc для сборки DOCX с reference.docx."""
    docx_cfg = config.get("docx")
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "docx+empty_paragraphs",
        "--standalone",
        "--filter", str(FILTER_FILE),
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
        "--reference-doc", str(docx_cfg.get("reference-file")),
    ]
    if config.get("trace"):
        cmd.append("--trace")
    if config.get("verbose"):
        cmd.append("--verbose")
    if docx_cfg.get("toc"):
        cmd.append("--toc")
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")



def _build_docx(
    project_path: Path,
    md_files: list[Path],
    config: dict,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает DOCX: pandoc + reference.docx.

    reference.docx: из config.yaml (docx.reference_doc) или bgen/reference.docx.
    Если файл не найден — предупреждение, Pandoc использует дефолтный шаблон.
    Возвращает путь к файлу. Бросает BgenError при ошибке Pandoc.
    """
    output_dir = Path(config.get("output-dir"))
    output_file = output_dir / f"{config.get("output-file-base")}.docx"
    keep_metadata = config.get("keep-metadata")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_docx_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "docx_metadata.yaml")
        _run_pandoc_docx(
            md_files, meta_path, output_file, project_path, config, env, warnings
        )

    return output_file


