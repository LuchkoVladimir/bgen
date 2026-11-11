"""EPUB: подготовка метаданных и вызов Pandoc."""
from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import BGEN_DIR, BgenError


def _build_epub_metadata(project_path: Path, config: dict, tmpdir: Path, warnings: list[str]) -> Path:
    """Готовит metadata.yaml для EPUB (title, author, lang).

    cover-image не передаётся в metadata: для EPUB обложка задаётся
    отдельным флагом --epub-cover-image.
    Возвращает путь к metadata.yaml.
    """
    meta = dict(config.get("metadata") or {})
    meta.setdefault("lang", "ru")

    if not meta.get("title"):
        raise BgenError("metadata.title не задан в config.yaml")
    if not meta.get("author"):
        raise BgenError("metadata.author не задан в config.yaml")

    # cover-image — для EPUB через --epub-cover-image, не в metadata
    meta.pop("cover-image", None)

    meta_path = tmpdir / "metadata.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)
    return meta_path


def _run_pandoc_epub(
    md_files: list[Path],
    meta_path: Path,
    output: Path,
    resource_path: Path,
    cover_path: Path | None,
    css_path: Path | None,
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
    if cover_path is not None and cover_path.exists():
        cmd.extend(["--epub-cover-image", str(cover_path)])
    if css_path is not None and css_path.exists():
        cmd.extend(["--css", str(css_path)])
    filter_path = BGEN_DIR / "filter_bgen.lua"
    if filter_path.exists():
        cmd.extend(["--lua-filter", str(filter_path)])
    abbrevs = BGEN_DIR / "abbrevs.txt"
    if abbrevs.exists():
        cmd.extend(["--abbreviations", str(abbrevs)])
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")


