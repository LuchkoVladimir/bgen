"""FB2: сборка одного формата (pandoc → postprocess → validate)."""
from __future__ import annotations

import subprocess
import shutil
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import BGEN_DIR, BgenError
from ..project import _get_body_files
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

    if not meta.get("title"):
        raise BgenError("metadata.title не задан в config.yaml")
    if not meta.get("author"):
        raise BgenError("metadata.author не задан в config.yaml")

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
        "--metadata-file", str(meta_path),
        "--resource-path", str(resource_path),
    ]
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
        cmd.append("--verbose")
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


def _build_fb2(
    project_path: Path,
    config: dict,
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
    output_name = fb2_cfg.get("output_name", "book.fb2")
    output_path = output_dir / output_name

    md_files = _get_body_files(project_path)

    keep_metadata = config.get("keep_metadata", False)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_path = _build_pandoc_metadata(project_path, config, tmpdir, warnings)
        if keep_metadata:
            shutil.copy(meta_path, output_dir / "fb2_metadata.yaml")   
        _run_pandoc_fb2(md_files, meta_path, output_path, project_path, config, env, warnings)

    # pandoc формирует fb2 со множеством проблем, поэтому требуется постобработка
    _postprocess_fb2(output_path, config, project_path, warnings)

    xsd_errors = _validate_fb2(output_path)
    if xsd_errors:
        error_text = "\n".join(xsd_errors)
        raise BgenError(f"FB2 не прошёл валидацию по XSD:\n{error_text}")

    return output_path


