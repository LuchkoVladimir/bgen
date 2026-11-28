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
from pathlib import Path

PROGRAM_NAME = "bgen"
PROGRAM_TITLE = "BookGenerator"
PROGRAM_VERSION = "2.7.0"

KNOWN_FORMATS = {"fb2", "docx", "epub", "txt"}

BGEN_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = BGEN_DIR / "schemas"
FB2_SCHEMAS_DIR = SCHEMAS_DIR / "fb2_xsd"

FILTER_FILE = BGEN_DIR / "lib_bgen" / "pandoc_filter.py"
FB2_XSD_FILE = FB2_SCHEMAS_DIR / "FictionBook.xsd"
CONFIG_SCHEMA_FILE = SCHEMAS_DIR / "config.schema.json"
TYPOGRAPHY_FILE = SCHEMAS_DIR / "typography.txt"
RULES_FILE = SCHEMAS_DIR / "rules.txt"
DOCX_REF_FILE = SCHEMAS_DIR / "reference.docx"
EPUB_CSS_FILE = SCHEMAS_DIR / "epub.css"

class BgenError(Exception):
    """Ошибка bgen, пригодная для показа пользователю."""


