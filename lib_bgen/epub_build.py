"""EPUB: сборка одного формата (pandoc + cover + css)."""
from __future__ import annotations

import subprocess
import shutil
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from .common import BGEN_DIR, BgenError
from .project import _get_body_files


def _build_epub_metadata(project_path: Path, config: dict, tmpdir: Path, warnings: list[str]) -> tuple[Path, Path | None, Path | None, Path | None]:
    """Готовит metadata.yaml для EPUB (title, author, lang).

    cover-image не передаётся в metadata: для EPUB обложка задаётся
    отдельным флагом --epub-cover-image.
    Возвращает пути к [metadata.yaml, epub-metadata.xml, epub-metadata-addon.yaml,  epub-cover-image-path].
    """
    meta = dict(config.get("metadata") or {})
    meta.setdefault("lang", "ru")

    if not meta.get("title"):
        raise BgenError("metadata.title не задан в config.yaml")
    if not meta.get("author"):
        raise BgenError("metadata.author не задан в config.yaml")

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

    # --epub-metadata c xml для epub
    epub_cfg = config.get("epub") or {}
    epub_meta_file_rel = epub_cfg.get("metadata-file", "")
    epub_meta_file_path = None
    if epub_meta_file_rel:
        epub_meta_file_path = (project_path / epub_meta_file_rel).resolve()
        if not epub_meta_file_path.exists():
            warnings.append(f"epub-metadata-file не найден: {epub_meta_file_path}")
            epub_meta_file_path = None

    # Дополнительный --metadata-file c yaml для epub
    add_meta = dict(epub_cfg.get("metadata") or {})
    epub_add_meta_path = None
    if epub_meta_file_path and add_meta:
        warnings.append(f"epub:metadata-file и epub:metadata оба не пусты: используем файл.")
        epub_add_meta_path = None
    elif add_meta:
        epub_add_meta_path = tmpdir / "epub-metadata-addon.yaml"

    if epub_add_meta_path:
        with open(epub_add_meta_path, "w", encoding="utf-8") as f:
            yaml.dump(add_meta, f, allow_unicode=True, default_flow_style=False)

    return meta_path, epub_meta_file_path, epub_add_meta_path, cover_path


def _run_pandoc_epub(
    md_files: list[Path],
    meta_path: Path,
    epub_meta_addon_path: Path | None,
    epub_meta_xml_path: Path | None,
    output: Path,
    resource_path: Path,
    cover_path: Path | None,
    css_path: Path | None,
    config: dict,
    toc: bool,
    env: dict,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc для сборки EPUB3 (cover, css, filter)."""
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "epub3",
        "--standalone",
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
    ]
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
        cmd.append("--verbose")
    if toc:
        cmd.append("--toc")
    if cover_path is not None and cover_path.exists():
        cmd.extend(["--epub-cover-image", str(cover_path)])
    if css_path is not None and css_path.exists():
        cmd.extend(["--css", str(css_path)])
    if epub_meta_addon_path is not None and epub_meta_addon_path.exists():
        cmd.extend(["--metadata-file", str(epub_meta_addon_path)])
    if epub_meta_xml_path is not None and epub_meta_xml_path.exists():
        cmd.extend(["--epub-metadata", str(epub_meta_xml_path)])

    filter_path = BGEN_DIR / "filter_bgen.lua"
    if filter_path.exists():
        cmd.extend(["--lua-filter", str(filter_path)])
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")


def _build_epub(
    project_path: Path,
    config: dict,
    output_dir: Path,
    env: dict,
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

    keep_metadata = config.get("keep_metadata", False)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, epub_meta_xml_path, epub_meta_addon_path, cover_path = _build_epub_metadata(
                project_path, config, tmpdir, warnings,
        )
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "epub_metadata.yaml")
            if epub_meta_addon_path is not None:
                shutil.copy(epub_meta_addon_path, output_dir / "epub_addon_metadata.yaml")
        _run_pandoc_epub(
            md_files, meta_path, epub_meta_addon_path, epub_meta_xml_path, output_path, project_path,
            cover_path, css_path, config, toc, env, warnings,
        )

    return output_path


