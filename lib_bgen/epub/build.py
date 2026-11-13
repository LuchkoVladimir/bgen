"""EPUB: сборка одного формата (pandoc + cover + css)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..common import BGEN_DIR
from ..project import _get_body_files
from .pandoc import _build_epub_metadata, _run_pandoc_epub


def _build_epub(
    project_path: Path,
    config: dict,
    output_dir: Path,
    warnings: list[str],
) -> Path:
    """Собирает EPUB: pandoc + обложка (metadata.cover-image) + CSS.

    cover-image: из config.yaml (metadata.cover-image), если файл есть.
    css: из config.yaml (epub.css) или bgen/epub.css (дефолтный).
    Если файл не найден — предупреждение, сборка продолжается.
    Возвращает путь к файлу. Бросает BgenError при ошибке Pandoc.
    """
    epub_cfg = config.get("epub") or {}
    output_name = epub_cfg.get("output_name", "book.epub")
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    # CSS: из config (epub.css) или bgen/epub.css
    css_rel = epub_cfg.get("css")
    if css_rel:
        css_path = (project_path / css_rel).resolve()
    else:
        css_path = BGEN_DIR / "epub.css"
    if css_path is None or not css_path.exists():
        warnings.append(f"CSS не найден: {css_path}. Используется дефолтный.")
        css_path = None

    # build table of contents
    toc = epub_cfg.get("toc", False)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, epub_meta_xml_path, epub_meta_addon_path, cover_path = _build_epub_metadata(
                project_path, config, tmpdir, warnings,
        )
        _run_pandoc_epub(
            md_files, meta_path, epub_meta_addon_path, epub_meta_xml_path, output_path, project_path,
            cover_path, css_path, toc, warnings,
        )

    return output_path


