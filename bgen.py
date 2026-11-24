#!/usr/bin/env python3
"""bgen: генератор цифровых книг из Markdown.

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
import argparse
import sys
from pathlib import Path

import lib_bgen

try:
    import yaml
except ImportError:
    raise ImportError("Требуется PyYAML. Установите: pip install pyyaml")


def cmd_build(args):
    warnings: list[str] = []
    try:
        results = lib_bgen.build(Path(args.path), only=args.only, warnings=warnings)
    except lib_bgen.BgenError as e:
        for w in warnings:
            print(f"Предупреждение: {w}", file=sys.stderr)
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    for w in warnings:
        print(f"Предупреждение: {w}", file=sys.stderr)
    for fmt, output_path in results:
        print(f"Готово ({fmt}): {output_path}")


def cmd_stat(args):
    try:
        stats = lib_bgen.stat(Path(args.path))
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    if stats is None:
        print("Не найдено текстовых файлов.")
        return

    print(f"Файлов учтено: {stats['files']}")
    print(f"Знаков с пробелами: {stats['chars_with_spaces']}")
    print(f"Знаков без пробелов: {stats['chars_no_spaces']}")
    print(f"Слов: {stats['words']}")


def cmd_cfg(args):
    try:
        config = lib_bgen.cfg(Path(args.path))
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    config_str = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"{config_str}")


def main():
    parser = argparse.ArgumentParser(
        prog="bgen",
        description="bgen: генератор цифровых книг из Markdown.",
    )
    parser.add_argument("-v", "--version", action="version",
                       version=f"{lib_bgen.PROGRAM_TITLE} ({lib_bgen.PROGRAM_NAME}) - v{lib_bgen.PROGRAM_VERSION}")

    sub = parser.add_subparsers(dest="command", metavar="КОМАНДА")

    # build book
    p_build = sub.add_parser(
        "build",
        help="собрать книгу в форматах, включённых в config.yaml",
    )
    p_build.add_argument("path", help="путь к проекту книги")
    p_build.add_argument(
        "--only",
        metavar="FMT[,FMT...]",
        help="собрать только указанные форматы (переопределяет config.yaml)",
    )
    p_build.set_defaults(func=cmd_build)

    # book statistics
    p_stat = sub.add_parser("stat", help="посчитать статистику текста")
    p_stat.add_argument("path", help="путь к проекту книги")
    p_stat.set_defaults(func=cmd_stat)

    # book project configuration
    p_cfg = sub.add_parser("cfg", help="показать построенную конфигурацию проекта")
    p_cfg.add_argument("path", help="путь к проекту книги")
    p_cfg.set_defaults(func=cmd_cfg)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()


