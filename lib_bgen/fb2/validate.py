"""FB2: валидация по XSD."""
from __future__ import annotations

from pathlib import Path

try:
    from lxml import etree as lxml_etree
except ImportError:
    raise ImportError("Требуется lxml. Установите: pip install lxml")

from ..common import SCHEMAS_DIR, BgenError
from .constants import FB2_XSD

def _validate_fb2(fb2_path: Path) -> list[str]:
    """Валидация FB2 по XSD. Возвращает список сообщений об ошибках.

    Если XSD-файл не найден — BgenError: без схемы валидация бессмысленна.
    """
    if not FB2_XSD.exists():
        raise BgenError(
            f"XSD-схема FB2 не найдена: {FB2_XSD}. "
            f"Положите FictionBook.xsd и связанные схемы в {SCHEMAS_DIR}"
        )

    try:
        schema_doc = lxml_etree.parse(str(FB2_XSD))
        schema = lxml_etree.XMLSchema(schema_doc)
    except lxml_etree.XMLSchemaParseError as e:
        raise BgenError(f"не удалось загрузить XSD-схему {FB2_XSD}: {e}")

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


