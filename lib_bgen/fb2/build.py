"""FB2: сборка одного формата (pandoc → postprocess → validate)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..common import BgenError
from ..project import _get_body_files
from .pandoc import _build_pandoc_metadata, _run_pandoc_fb2
from .postprocess import _postprocess_fb2
from .validate import _validate_fb2


def _build_fb2(project_path: Path, config: dict, output_dir: Path) -> tuple[Path, list[str]]:
    """Собирает FB2: pandoc, постобработка, XSD-валидация.

    Возвращает (путь к файлу, предупреждения). Бросает BgenError при ошибке.
    """
    fb2_cfg = config.get("fb2") or {}
    output_name = fb2_cfg.get("output_name", "book.fb2")
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path, meta_warnings = _build_pandoc_metadata(project_path, config, tmpdir)
        warnings.extend(meta_warnings)
        warnings.extend(_run_pandoc_fb2(md_files, meta_path, output_path, project_path))

    # pandoc формирует fb2 со множеством проблем, поэтому требуется постобработка
    warnings.extend(_postprocess_fb2(output_path, config, project_path))

    xsd_errors = _validate_fb2(output_path)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    return output_path, warnings


