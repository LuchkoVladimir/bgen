"""TXT (plain): сборка одного формата (pandoc → файл)."""
from __future__ import annotations

from pathlib import Path

from ..project import _get_body_files
from .pandoc import _run_pandoc_txt


def _make_card(config: dict) -> str:
    """Формирует карточку книги для TXT: автор(ы), название, пустая строка.

    Авторы — каждый на новой строке. Название — после авторов.
    Если title/author нет — возвращает пустую строку (карточка не нужна).
    """
    meta = config.get("metadata") or {}
    title = meta.get("title") or ""
    authors = meta.get("author") or []
    if isinstance(authors, str):
        authors = [authors]
    authors = [str(a) for a in authors if a]

    if not title or not authors:
        return ""

    lines = authors + [title, ""]
    return "\n".join(lines) + "\n"



def _build_txt(
    project_path: Path,
    config: dict,
    output_dir: Path,
    env: dict,
    warnings: list[str],
) -> Path:
    """Собирает TXT (plain): pandoc -t plain --columns N --wrap W.

    Без metadata.yaml, без --standalone. Постобработка: карточка (author, title)
    в начало, если config.yaml: txt.card: true.
    Возвращает путь к файлу. Бросает BgenError при ошибке Pandoc.
    """
    txt_cfg = config.get("txt") or {}
    output_name = txt_cfg.get("output_name", "book.txt")
    output_path = output_dir / output_name

    columns = txt_cfg.get("columns", 80)
    wrap = txt_cfg.get("wrap", "auto")
    card = txt_cfg.get("card", False)

    md_files = _get_body_files(project_path)

    _run_pandoc_txt(
        md_files, output_path, project_path, columns, wrap, config, env, warnings,
    )

    if card:
        card_text = _make_card(config)
        if card_text:
            body = output_path.read_text(encoding="utf-8")
            output_path.write_text(card_text + "\n" + body, encoding="utf-8")

    return output_path


