"""DOCX: подготовка метаданных и вызов Pandoc."""
from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import BGEN_DIR, BgenError


def _build_docx_metadata(project_path: Path, config: dict, tmpdir: Path, warnings: list[str]) -> Path:
    """Готовит metadata.yaml для Pandoc (DOCX).

    DOCX не использует coverpage, поэтому cover-image не передаётся.
    Возвращает путь к metadata.yaml.
    """
    meta = dict(config.get("metadata") or {})
    meta.setdefault("lang", "ru")

    if not meta.get("title"):
        raise BgenError("metadata.title не задан в config.yaml")
    if not meta.get("author"):
        raise BgenError("metadata.author не задан в config.yaml")

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
    reference_doc: Path,
    toc: bool,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc для сборки DOCX с reference.docx."""
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "docx+empty_paragraphs",
        "--standalone",
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
        "--reference-doc", str(reference_doc),
    ]
    if toc:
        cmd.append("--toc")
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


