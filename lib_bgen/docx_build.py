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

from .common import FILTER_FILE, BgenError
from .project import _get_body_files


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
        "--lua-filter", str(FILTER_FILE),
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
    output_path = output_dir / f"{config.get("output-file-base")}.docx"
    md_files = _get_body_files(project_path)
    keep_metadata = config.get("keep-metadata")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_docx_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "docx_metadata.yaml")
        _run_pandoc_docx(
            md_files, meta_path, output_path, project_path, config, env, warnings
        )

    return output_path


