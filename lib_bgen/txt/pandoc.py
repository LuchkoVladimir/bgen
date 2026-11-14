"""TXT (plain): вызов Pandoc."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..common import BGEN_DIR, BgenError


def _run_pandoc_txt(
    md_files: list[Path],
    output: Path,
    resource_path: Path,
    columns: int,
    wrap: str,
    config: dict,
    warnings: list[str],
) -> None:
    """Вызывает Pandoc: -t plain --columns N --wrap W.

    Без metadata.yaml (plain не использует метаданные).
    Без --standalone (не нужен).
    С Lua-фильтром (для .q/.qq и будущей типографики).
    """
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--to", "plain",
        "--columns", str(columns),
        "--wrap", wrap,
        "--resource-path", str(resource_path),
    ]
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
        cmd.append("--verbose")
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


