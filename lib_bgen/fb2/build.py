"""FB2: сборка одного формата (pandoc → postprocess → validate).

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
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import FILTER_FILE, BgenError
from .postprocess import _postprocess_fb2
from .validate import _validate_fb2


def _build_pandoc_metadata(
    project_path: Path,
    config: dict,
    tmpdir: Path,
    warnings: list[str],
) -> Path:
    """Готовит metadata.yaml для Pandoc: резолвит cover-image, ставит lang по умолчанию.

    warnings - внешний, для добавления предупреждений
    Возвращает путь к metadata.yaml.
    """
    meta = dict(config.get("metadata"))
    meta.setdefault("lang", "ru")

    cover = meta.get("cover-image")
    if cover:
        cover_path = (project_path / cover).resolve()
        if cover_path.exists():
            meta["cover-image"] = str(cover_path)
        else:
            warnings.append(f"обложка не найдена, пропускаем: {cover_path}")
            meta.pop("cover-image")

    meta_path = tmpdir / "metadata.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)
    return meta_path


def _run_pandoc_fb2(
    md_files: list[Path],
    meta_path: Path,
    output: Path,
    resource_path: Path,
    wrap_mode: str,
    config: dict,
    env: dict,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc для сборки FB2."""
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "fb2",
        "--standalone",
        "--filter", str(FILTER_FILE),
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
        "--wrap", wrap_mode,
    ]
    if config.get("trace"):
        cmd.append("--trace")
    if config.get("verbose"):
        cmd.append("--verbose")
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")


def _build_fb2(
    project_path: Path,
    md_files: list[Path],
    config: dict,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает FB2: pandoc, постобработка, XSD-валидация.

    warnings — внешний список; все предупреждения (включая накопленные
    до BgenError) пишутся в него. Возвращает путь к файлу.
    Бросает BgenError при ошибке.
    Возвращает (путь к файлу).
    """
    output_dir = Path(config.get("output-dir"))
    output_file = output_dir / f"{config.get("output-file-base")}.fb2"
    fb2_cfg = config.get("fb2")
    keep_metadata = config.get("keep-metadata")

    # print mode: pretty/toleft/src → wrap_mode
    print_mode = fb2_cfg.get("print-mode")
    wrap_map = {
        "pretty": "auto",
        "toleft": "auto",
        "src": "preserve",
    }
    wrap_mode = wrap_map.get(print_mode)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_pandoc_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "fb2_metadata.yaml")   
        _run_pandoc_fb2(md_files, meta_path, output_file, project_path, wrap_mode, config, env, warnings)

    # pandoc формирует fb2 со множеством проблем, поэтому требуется постобработка
    _postprocess_fb2(output_file, config, warnings)

    xsd_errors = _validate_fb2(output_file)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    # fb2.zip: сжать рядом (не вместо)
    if fb2_cfg.get("zip"):
        zip_path = output_file.with_suffix(output_file.suffix + ".zip")  # book.fb2.zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(output_file, arcname=output_file.name)
        warnings.append(f"FB2 зазипован: {zip_path}")

    return output_file


