"""EPUB: подготовка метаданных и вызов Pandoc."""
from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import BGEN_DIR, BgenError


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
    """Вызывает Pandoc для сборки EPUB3 (cover, css, filter, abbrevs)."""
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
    abbrevs = BGEN_DIR / "abbrevs.txt"
    if abbrevs.exists():
        cmd.extend(["--abbreviations", str(abbrevs)])
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")


