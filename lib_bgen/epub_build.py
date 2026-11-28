"""EPUB: сборка одного формата (pandoc + cover + css).

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

import subprocess
import shutil
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from .common import FILTER_FILE, BgenError


def _build_epub_metadata(
    project_path: Path,
    config: dict,
    tmpdir: Path,
    warnings: list[str]
) -> tuple[Path, Path | None, Path | None, Path | None]:
    """Готовит metadata.yaml для EPUB (title, author, lang).

    cover-image не передаётся в metadata: для EPUB обложка задаётся
    отдельным флагом --epub-cover-image.
    Возвращает пути к [metadata.yaml, epub-metadata.xml, epub-metadata-addon.yaml,  epub-cover-image-path].
    """
    meta = dict(config.get("metadata"))
    meta.setdefault("lang", "ru")

    meta_path = tmpdir / "metadata.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)

    # Обложка: из metadata.cover-image (тот же, что для FB2)
    cover_rel = meta.get("cover-image")
    cover_path = None
    if cover_rel:
        cover_path = (project_path / cover_rel).resolve()
        if not cover_path.exists():
            warnings.append(f"обложка не найдена: {cover_path}")
            cover_path = None

    # Выбираем дополнительную metadata
    epub_cfg = config.get("epub")
    add_meta_mode = epub_cfg.get("add-meta-mode")

    add_meta_yaml_path = None
    add_meta_xml_path = None

    if add_meta_mode == "xml":
        add_meta_xml_path = epub_cfg.get("add-meta-xml-file")
    elif add_meta_mode == "yaml":
        add_meta_yaml = dict(epub_cfg.get("add-meta-yaml"))
        add_meta_yaml_path = tmpdir / "epub-metadata-addon.yaml"
        with open(add_meta_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(add_meta_yaml, f, allow_unicode=True, default_flow_style=False)

    return meta_path, add_meta_xml_path, add_meta_yaml_path, cover_path


def _run_pandoc_epub(
    md_files: list[Path],
    meta_path: Path,
    add_meta_yaml_path: Path | None,
    add_meta_xml_path: Path | None,
    output: Path,
    resource_path: Path,
    cover_path: Path | None,
    config: dict,
    env: dict,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc для сборки EPUB3 (cover, css, filter)."""
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "epub3",
        "--standalone",
        "--filter", str(FILTER_FILE),
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
    ]

    epub_cfg = config.get("epub")

    if config.get("trace"):
        cmd.append("--trace")
    if config.get("verbose"):
        cmd.append("--verbose")
    if epub_cfg.get("toc"):
        cmd.append("--toc")
    if cover_path is not None and cover_path.exists():
        cmd.extend(["--epub-cover-image", str(cover_path)])

    cmd.extend(["--css", str(epub_cfg.get("css-file"))])

    if add_meta_yaml_path is not None:
        cmd.extend(["--metadata-file", str(add_meta_yaml_path)])
    if add_meta_xml_path is not None:
        cmd.extend(["--epub-metadata", str(add_meta_xml_path)])

    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")


def _build_epub(
    project_path: Path,
    md_files: list[Path],
    config: dict,
    output_dir: Path,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает EPUB: pandoc + обложка (metadata.cover-image) + CSS.

    cover-image: из config.yaml (metadata.cover-image), если файл есть.
    css: из config.yaml (epub.css-file) или bgen/schemas/epub.css (дефолтный).
    Если файл не найден — предупреждение, сборка продолжается.
    Возвращает путь к файлу. Бросает BgenError при ошибке Pandoc.
    """
    output_path = output_dir / f"{config.get("output-file-base")}.epub"
    keep_metadata = config.get("keep-metadata")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, add_meta_xml_path, add_meta_yaml_path, cover_path = _build_epub_metadata(
                project_path, config, tmpdir, warnings,
        )
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "epub_metadata.yaml")
            if add_meta_yaml_path is not None:
                shutil.copy(add_meta_yaml_path, output_dir / "epub_addon_metadata.yaml")
        _run_pandoc_epub(
            md_files, meta_path, add_meta_yaml_path, add_meta_xml_path, output_path, project_path,
            cover_path, config, env, warnings,
        )

    return output_path


