"""FB2: константы формата (namespace, порядок элементов, схема)."""
from ..common import SCHEMAS_DIR
from ..common import PROGRAM_NAME
from ..common import PROGRAM_TITLE
from ..common import PROGRAM_VERSION

PROGRAM_USED = f"{PROGRAM_TITLE}: {PROGRAM_NAME}-{PROGRAM_VERSION}"

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

FB2_XSD = SCHEMAS_DIR / "FictionBook.xsd"

_TITLE_INFO_ORDER = [
    "genre", "author", "book-title", "annotation", "keywords",
    "date", "coverpage", "lang", "src-lang", "translator", "sequence",
]
_DOC_INFO_ORDER = [
    "author", "program-used", "date", "src-url", "src-ocr",
    "id", "version", "history", "publisher",
]
