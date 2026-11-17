"""FB2: сборка одного формата (pandoc → postprocess → validate)."""
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
from ..project import _get_body_files, PATHS_FB2_DESC
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
    meta = dict(config.get("metadata") or {})
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
        "--lua-filter", str(FILTER_FILE),
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
        "--wrap", wrap_mode,
    ]
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
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
    config: dict,
    paths: dict[str, Path | None],
    output_dir: Path,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает FB2: pandoc, постобработка, XSD-валидация.

    warnings — внешний список; все предупреждения (включая накопленные
    до BgenError) пишутся в него. Возвращает путь к файлу.
    Бросает BgenError при ошибке.
    Возвращает (путь к файлу).
    """
    fb2_cfg = config.get("fb2") or {}
    output_file_base = config.get("output-file-base", "book")
    output_name = output_file_base + ".fb2"
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    keep_metadata = config.get("keep-metadata", False)

    # print mode: pretty/toleft/src → wrap_mode
    print_mode = fb2_cfg.get("print-mode", "pretty")
    wrap_map = {
        "pretty": "auto",
        "toleft": "auto",
        "src": "preserve",
    }
    wrap_mode = wrap_map.get(print_mode, "auto")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_pandoc_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "fb2_metadata.yaml")   
        _run_pandoc_fb2(md_files, meta_path, output_path, project_path, wrap_mode, config, env, warnings)

    # pandoc формирует fb2 со множеством проблем, поэтому требуется постобработка
    _postprocess_fb2(output_path, config, paths[PATHS_FB2_DESC], warnings)

    xsd_errors = _validate_fb2(output_path)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    # fb2.zip: сжать рядом (не вместо)
    if fb2_cfg.get("zip", False):
        zip_path = output_path.with_suffix(output_path.suffix + ".zip")  # book.fb2.zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(output_path, arcname=output_path.name)
        warnings.append(f"FB2 зазипован: {zip_path}")

    return output_path


