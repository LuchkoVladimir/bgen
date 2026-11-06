"""FB2: подготовка метаданных и вызов Pandoc."""
from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

from ..common import BGEN_DIR, BgenError


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


