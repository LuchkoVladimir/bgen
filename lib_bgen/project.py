"""Проект книги: конфигурация, файлы, статистика.

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

import copy
import os
import re
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")

try:
    import jsonschema
    from jsonschema import validators
except ImportError:
    raise ImportError("Требуется jsonschema. Установите: pip install jsonschema")

from .common import (
    BgenError,
    FILTER_FILE,
    CONFIG_SCHEMA_FILE,
    TYPOGRAPHY_FILE,
    RULES_FILE,
    DOCX_REF_FILE,
    EPUB_CSS_FILE,
    )

KNOWN_FORMATS = {"fb2", "docx", "epub", "txt"}

# ============================================================
# Конфигурация
# ============================================================
def _resolve_file_paths(project_path: Path, config: dict) -> dict:
    """Эффективные пути к «дополнительным файлам» проекта.

    Не проверяет существование — только выбирает путь (конфиг → bgen/schemas).
    Возвращает модифицированный путями конфиг.
    """
    fb2_cfg = config.get("fb2")
    docx_cfg = config.get("docx")
    epub_cfg = config.get("epub")

    missing: list[str] = []

    # config → bgen/schemas/typography.txt
    file = config.get("typography-file")
    file_path = (project_path / file).resolve() if file else TYPOGRAPHY_FILE
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        config["typography-file"] = str(file_path)

    # config → bgen/schemas/rules.txt
    file = config.get("rules-file")
    file_path = (project_path / file).resolve() if file else RULES_FILE
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        config["rules-file"] = str(file_path)

    # config → bgen/schemas/reference.docx
    file = docx_cfg.get("reference-file")
    file_path = (project_path / file).resolve() if file else DOCX_REF_FILE
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        docx_cfg["reference-file"] = str(file_path)

    # config → bgen/schemas/epub.css
    file = epub_cfg.get("css-file")
    file_path = (project_path / file).resolve() if file else EPUB_CSS_FILE
    if not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    else:
        epub_cfg["css-file"] = str(file_path)

    # Тут нет дефолтных файлов в репозитории, поэтому файлы могут и отсутствовать и тогда не подменяются

    # только если задан description-file
    file = fb2_cfg.get("description-file")
    file_path = (project_path / file).resolve() if file else None
    if file_path and not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    elif file_path:
        fb2_cfg["description-file"] = str(file_path)

    # только если задан add-meta-xml-file
    file = epub_cfg.get("add-meta-xml-file")
    file_path = (project_path / file).resolve() if file else None
    if file_path and not file_path.exists():
        missing.append(f"файл не найден: {file_path}")
    elif file_path:
        epub_cfg["add-meta-xml-file"] = str(file_path)

    if missing:
        raise BgenError("\n".join(missing))

    return config


def _extend_with_default(validator_class):
    """Расширяет валидатор jsonschema: перед проверкой properties
    подставляет default из схемы для отсутствующих ключей.

    Внимание: работает только внутри уже существующих объектов
    (для секций нужен default: {}, для массивов - []).
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for prop, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(prop, copy.deepcopy(subschema["default"]))
        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return validators.extend(validator_class, {"properties": set_defaults})


DefaultValidatingValidator = _extend_with_default(jsonschema.Draft202012Validator)


def _build_config(project_path: Path) -> dict:
    """Читает config.yaml, валидирует по схеме и заполняет дефолтами.

    Возвращает полную валидную конфигу (или бросает BgenError).
    Дефолты берутся из config.schema.json (ключ default).
    """
    config_path = project_path / "config.yaml"
    if not config_path.exists():
        raise BgenError(f"{config_path} не найден")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if not CONFIG_SCHEMA_FILE.exists():
        raise BgenError(
            f"схема конфига не найдена: {CONFIG_SCHEMA_FILE}. "
            f"Проверьте дистрибутив bgen."
        )

    try:
        with open(CONFIG_SCHEMA_FILE, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise BgenError(
            f"не удалось загрузить схему конфига {CONFIG_SCHEMA_FILE}: {e}"
        )

    validator = DefaultValidatingValidator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))

    if errors:
        lines = []
        for err in errors:
            path = ".".join(str(p) for p in err.absolute_path) or "(root)"
            lines.append(f"  {path}: {err.message}")
        raise BgenError(
            "config.yaml не прошёл валидацию по схеме:\n" + "\n".join(lines)
        )

    config = _resolve_file_paths(project_path, config)

    return config


def _validate_project_path(project_path: Path) -> Path:
    """Проверяет, что путь — существующая директория. Возвращает resolve()."""
    project_path = project_path.resolve()
    if not project_path.is_dir():
        raise BgenError(f"{project_path} не директория")
    return project_path


def _resolve_formats(config: dict, only: str | None) -> list[str]:
    """Определяет список форматов для сборки.

    only — строка "fb2,epub" из CLI; переопределяет config.
    Иначе — секции config с enabled: true.
    """
    if only:
        formats = [f.strip() for f in only.split(",") if f.strip()]
        unknown = [f for f in formats if f not in KNOWN_FORMATS]
        if unknown:
            raise BgenError(f"неизвестный формат: {', '.join(unknown)}")
        return formats

    formats = []
    for fmt in KNOWN_FORMATS:
        section = config.get(fmt)
        if section.get("enabled"):
            formats.append(fmt)

    if not formats:
        raise BgenError("не включено ни одного формата (проверьте config.yaml)")

    return formats


# ============================================================
# Файлы
# ============================================================

def _get_body_files(project_path: Path) -> list[Path]:
    """Возвращает отсортированные .md файлы из body/ (рекурсивно)."""
    body_dir = project_path / "body"
    if not body_dir.exists():
        raise BgenError(f"директория {body_dir} не найдена")
    files = sorted(body_dir.rglob("*.md"))
    if not files:
        raise BgenError(f"в {body_dir} не найдено .md файлов")
    return files


# ============================================================
# Конфигурация
# ============================================================

def cfg(project_path: Path) -> tuple[dict, list[str], str]:
    """Конфигурация проекта. Возвращает конфигу, авторов и название."""
    project_path = _validate_project_path(project_path)
    config = _build_config(project_path)
    authors = config.get("metadata").get("author")
    title = config.get("metadata").get("title")
    return config, authors, title


# ============================================================
# Статистика
# ============================================================

def _strip_markdown(project_path: Path, file: Path, pandoc_env: dict) -> str:
    """Удаляет Markdown-разметку для статистики."""
    cmd = [
        "pandoc",
        "--from", "markdown",
        "--filter", str(FILTER_FILE),
        "--to", "plain-strikeout",
        "--resource-path", str(project_path),
        str(file)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=pandoc_env)
    if result.returncode != 0:
        raise BgenError(f"pandoc завершился с ошибкой:\n{result.stderr}")
    return result.stdout


def _get_stat_from_md(config: dict, project_path: Path, files: list[Path]) -> dict[Path, tuple[int, int]]:
    """Считает объёмные метрики по списку .md файлов."""
    pandoc_env = _build_pandoc_env(config, for_chars_count = True)
    converted_files: dict[Path, tuple[int, int]] = {}
    for file in files:
        stripped = _strip_markdown(project_path, file, pandoc_env)
        words = re.findall(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*", stripped)
        converted_files[file.relative_to(project_path / "body")] = [len(words), len(stripped)]
    return converted_files


def stat(project_path: Path) -> tuple[dict[Path, tuple[int, int]], list[str], str]:
    """Статистика текста проекта. Возвращает dict с данными по каждому файлу, авторов и название."""
    project_path = _validate_project_path(project_path)
    files = _get_body_files(project_path)
    config = _build_config(project_path)
    authors = config.get("metadata").get("author")
    title = config.get("metadata").get("title")
    return _get_stat_from_md(config, project_path, files), authors, title


# ============================================================
# Проверка по правилам
# ============================================================

_RULE_RE = re.compile(r'^RULE:(\d+):"(.+)"$')


def parse_rules(path: Path, rules: list[int] | None) -> dict[int, tuple[str, str, list[tuple[int, str, str]]]]:
    """
    Читает файл с правилами вида:

        RULE:XXX:pattern
        Описание правила, возможно многострочное.
        Пустая строка или следующий RULE завершает описание.

    Возвращает dict:
        {номер: (pattern, описание, [])}

    Список находок (третий элемент) пуст - заполняется отдельным анализом.
    """
    result: dict[int, tuple[str, str, list[tuple[int, str, str]]]] = {}

    text = path.read_text(encoding="utf-8")
    # нормализуем переводы строк, чтобы \r\n и \r не мешали
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    number: int | None = None
    pattern = ""
    desc: list[str] = []

    def flush() -> None:
        if number is not None:
            result[number] = (pattern, "\n".join(desc).strip(), [])

    for line in text.split("\n"):
        if m := _RULE_RE.match(line):
            flush()
            number = int(m.group(1))   # "001" -> 1, "01" -> 1, "1" -> 1
            pattern = m.group(2)
            desc = []
        elif not line.strip():
            flush()
            number = None
        elif number is not None:
            desc.append(line)

    flush()  # последнее правило, если файл кончился без пустой строки

    if rules is not None:
        allowed = set(rules)
        result = {k: v for k, v in result.items() if k in allowed}

    return result


def parse_files_with_rules(
    project_path: Path,
    files: list[Path],
    rules: dict[int, tuple[str, str, list[tuple[int, str, str]]]],
) -> dict[int, tuple[str, str, list[tuple[int, str, str]]]]:
    """
    Проходит по files, ищет в каждой строке паттерны из rules и дозаполняет
    третий элемент каждого правила - список находок (line_no, file_name, line).

    Параметры:
        project_path - путь к проекту
        files - список путей к файлам для анализа.
        rules - результат parse_rules(); мутируется (findings дополняются).

    Возвращает тот же rules (для удобства цепочки).
    """
    # Предкомпилируем регексы один раз, а не на каждую строку.
    compiled: dict[int, re.Pattern[str]] = {}
    for num, (pattern, _desc, _findings) in rules.items():
        try:
            compiled[num] = re.compile(pattern)
        except re.error as e:
            raise ValueError(
                f"правило {num}: некорректный регекс {pattern!r}: {e}"
            ) from e

    for file in files:
        # читаем как текст, нормализуем переводы строк
        text = file.read_text(encoding="utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # имя файла для отчёта - часть от body
        fname = file.relative_to(project_path / "body")

        for line_no, line in enumerate(text.split("\n"), start=1):
            for num, (pattern, _desc, findings) in rules.items():
                hit = compiled[num].search(line) is not None
                if hit:
                    findings.append((line_no, fname, line))

    return rules


def check(
        project_path: Path,
        list_rules: bool,
        rules_ids: str | None = None,
) -> tuple[dict[int, tuple[str, str, list[tuple[int, str, str]]]], list[str], str]:
    """Статистика текста проекта. Возвращает dict с результатами проверки по правилам, авторов и название.
        result: dict[int, tuple[str, str, list[tuple[int, str, str]]]] = {
                1: (
                    "Паттерн_1",
                    "Описание первого правила.\nВозможно и в несколько строк.",
                    [
                        (237, "some_file_name.md" , "Сам текст из исходника."),
                        (25, "some2_file_name.md" , "В котором была найдена ошибка."),
                        (318, "some2_file_name.md" , "И ещё из исходника."),
                    ],
                ),
                2: (
                    "Паттерн_2",
                    "Описание второго правила.",
                    [
                        (112, "some2_file_name.md" , "Текст из исходника."),
                        (5, "some3_file_name.md" , "И ещё."),
                    ],
                ),
            }
    """
    project_path = _validate_project_path(project_path)
    files = _get_body_files(project_path)
    config = _build_config(project_path)

    authors = config.get("metadata").get("author")
    title = config.get("metadata").get("title")
    rules_file = Path(config.get("rules-file"))

    if rules_ids is not None:
        rules_values = [int(r.strip()) for r in rules_ids.split(",") if r.strip()]
    else:
        rules_values = None

    rules = parse_rules(rules_file, rules_values)

    if list_rules:
        result = rules;
    else:
        result = parse_files_with_rules(project_path, files, rules)

    return result, authors, title


# ============================================================
# Сборка
# ============================================================

def _build_pandoc_env(config: dict, for_chars_count: bool = False) -> dict:
    env = os.environ.copy()
    env["BGEN_TYPOGRAPHY"] = str(config.get("typography-file"))
    if for_chars_count:
        env["BGEN_INLINE_MODE"] = "none"
    else:
        env["BGEN_INLINE_MODE"] = str(config.get("txt").get("inline-mode"))
    return env


def build(
        project_path: Path,
        only: str | None = None,
        warnings: list[str] | None = None,
) -> list[tuple[str, Path]]:
    """Собирает книгу в форматах из config.yaml (или из only).

    warnings — внешний список: все предупреждения (включая накопленные
    до BgenError) пишутся в него. Если None — создаётся локальный.
    Возвращает список (формат, путь к файлу).
    """
    if warnings is None:
        warnings = []

    project_path = _validate_project_path(project_path)
    config = _build_config(project_path)

    formats = _resolve_formats(config, only)

    output_dir = project_path / config.get("output-dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _build_pandoc_env(config)

    results: list[tuple[str, Path]] = []
    for fmt in formats:
        if fmt == "fb2":
            from .fb2.build import _build_fb2
            output_path = _build_fb2(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "docx":
            from .docx_build import _build_docx
            output_path = _build_docx(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "epub":
            from .epub_build import _build_epub
            output_path = _build_epub(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        elif fmt == "txt":
            from .txt_build import _build_txt
            output_path = _build_txt(project_path, config, output_dir, env, warnings)
            results.append((fmt, output_path))
        else:
            raise BgenError(f"формат {fmt} ещё не реализован")
    return results


