""" Общие константы и исключения bgen (не зависят от формата).

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
import os
from pathlib import Path

PROGRAM_NAME = "bgen"
PROGRAM_TITLE = "BookGenerator"
PROGRAM_VERSION = "2.4.0"

BGEN_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = BGEN_DIR / "schemas"
TYPOGRAPHY_FILE = SCHEMAS_DIR / "typography.txt"
FILTER_FILE = BGEN_DIR / "lib_bgen" / "pandoc_filter.py"

KNOWN_FORMATS = {"fb2", "docx", "epub", "txt"}


class BgenError(Exception):
    """Ошибка bgen, пригодная для показа пользователю."""


def _build_pandoc_env(config: dict, for_chars_count: bool = False) -> dict:
    env = os.environ.copy()
    env["BGEN_TYPOGRAPHY"] = str(config.get("typography-file"))
    if for_chars_count:
        env["BGEN_INLINE_MODE"] = "none"
    else:
        env["BGEN_INLINE_MODE"] = str(config.get("txt").get("inline-mode"))
    return env


