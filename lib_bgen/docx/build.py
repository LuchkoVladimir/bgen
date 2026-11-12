"""DOCX: сборка одного формата (pandoc → build)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..common import BGEN_DIR
from ..project import _get_body_files
from .pandoc import _build_docx_metadata, _run_pandoc_docx


def _build_docx(
    project_path: Path,
    config: dict,
    output_dir: Path,
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

    toc = docx_cfg.get("toc", False)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_docx_metadata(project_path, config, tmpdir, warnings)
        _run_pandoc_docx(
            md_files, meta_path, output_path, project_path, ref_path, toc, warnings
        )

    return output_path


