"""DOCX: сборка одного формата (pandoc → build)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from .common import BGEN_DIR, BgenError
from .project import _get_body_files


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
    config: dict,
    toc: bool,
    env: dict,
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
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
        cmd.append("--verbose")
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

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")



def _build_docx(
    project_path: Path,
    config: dict,
    output_dir: Path,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает DOCX: pandoc + reference.docx.

    reference.docx: из config.yaml (docx.reference_doc) или bgen/reference.docx.
    Если файл не найден — предупреждение, Pandoc использует дефолтный шаблон.
    Возвращает путь к файлу. Бросает BgenError при ошибке Pandoc.
    """
    docx_cfg = config.get("docx") or {}
    output_name = docx_cfg.get("output_name", "book.docx")
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    ref = docx_cfg.get("reference_doc")
    if ref:
        ref_path = (project_path / ref).resolve()
    else:
        ref_path = BGEN_DIR / "reference.docx"
    if not ref_path.exists():
        warnings.append(
            f"reference.docx не найден: {ref_path}. "
            f"Стили (Epigraph, Annotation и т.д.) не будут применены."
        )

    keep_metadata = config.get("keep_metadata", False)

    toc = docx_cfg.get("toc", False)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_docx_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "docx_metadata.yaml")
        _run_pandoc_docx(
            md_files, meta_path, output_path, project_path, ref_path, config, toc, env, warnings
        )

    return output_path


