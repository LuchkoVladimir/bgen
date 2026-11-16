"""Общие константы и исключения bgen (не зависят от формата)."""
from pathlib import Path

PROGRAM_NAME = "bgen"
PROGRAM_TITLE = "BookGenerator"
PROGRAM_VERSION = "1.0"

BGEN_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = BGEN_DIR / "schemas"
TYPOGRAPHY_FILE = SCHEMAS_DIR / "typography.txt"
FILTER_FILE = BGEN_DIR / "filter_bgen.lua"

KNOWN_FORMATS = {"fb2", "docx", "epub", "txt"}


class BgenError(Exception):
    """Ошибка bgen, пригодная для показа пользователю."""
