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
        stats, config = lib_bgen.stat(Path(args.path))
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    if stats is None:
        print("Не найдено текстовых файлов.")
        return

    print(f"Конфигурация: {config}")
    print(f"Файлов учтено: {stats['files']}")
    print(f"Знаков с пробелами: {stats['chars_with_spaces']}")
    print(f"Знаков без пробелов: {stats['chars_no_spaces']}")
    print(f"Слов: {stats['words']}")


def main():
    parser = argparse.ArgumentParser(
        prog="bgen",
        description="bgen: генератор цифровых книг из Markdown.",
    )
    sub = parser.add_subparsers(dest="command", metavar="КОМАНДА")

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

    p_stat = sub.add_parser("stat", help="посчитать статистику текста")
    p_stat.add_argument("path", help="путь к проекту книги")
    p_stat.set_defaults(func=cmd_stat)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()


