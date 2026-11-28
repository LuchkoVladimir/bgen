"""FB2: валидация по XSD.

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

from pathlib import Path

try:
    from lxml import etree as lxml_etree
except ImportError:
    raise ImportError("Требуется lxml. Установите: pip install lxml")

from .common import FB2_XSD_FILE, BgenError


def _validate_fb2(fb2_path: Path) -> list[str]:
    """Валидация FB2 по XSD. Возвращает список сообщений об ошибках.

    Если XSD-файл не найден — BgenError: без схемы валидация бессмысленна.
    """
    try:
        schema_doc = lxml_etree.parse(str(FB2_XSD_FILE))
        schema = lxml_etree.XMLSchema(schema_doc)
    except lxml_etree.XMLSchemaParseError as e:
        raise BgenError(f"не удалось загрузить XSD-схему {FB2_XSD_FILE}: {e}")

    try:
        doc = lxml_etree.parse(str(fb2_path))
    except lxml_etree.XMLSyntaxError as e:
        return [f"FB2 не является well-formed XML: {e}"]

    if schema.validate(doc):
        return []

    errors = []
    for err in schema.error_log:
        errors.append(f"XSD: строка {err.line}, столбец {err.column}: {err.message}")
    return errors


