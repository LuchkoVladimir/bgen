"""TXT (plain): сборка одного формата (pandoc → файл)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import FILTER_FILE, BgenError
from .project import _get_body_files


def _run_pandoc_txt(
    md_files: list[Path],
    output: Path,
    resource_path: Path,
    columns: int,
    wrap: str,
    config: dict,
    env: dict,
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
        "--lua-filter", str(FILTER_FILE),
        "--resource-path", str(resource_path),
    ]
    if config.get("trace", False):
        cmd.append("--trace")
    if config.get("verbose", False):
        cmd.append("--verbose")
    cmd.extend(["-o", str(output)])
    cmd.extend(str(p) for p in md_files)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    if result.stderr:
        warnings.append(f"pandoc: {result.stderr.strip()}")



def _make_card(config: dict) -> str:
    """Формирует карточку книги для TXT: автор(ы), название, пустая строка.

    Авторы — каждый на новой строке. Название — после авторов.
    Если title/author нет — возвращает пустую строку (карточка не нужна).
    """
    meta = config.get("metadata")
    title = meta.get("title")
    authors = meta.get("author")
    if isinstance(authors, str):
        authors = [authors]
    authors = [str(a) for a in authors if a]

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


