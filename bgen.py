#!/usr/bin/env python3
"""bgen: генератор цифровых книг из Markdown."""
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


