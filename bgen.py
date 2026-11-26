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


# ============================================================
# Оформление вывода
# ============================================================

def print_cfg_stat_check_line(type: str) -> None:
    match type:
        case "long":
            print("---------------------------------------")
        case "short":
            print("-----")


def print_cfg_stat_check_title(authors: list[str], title: str) -> None:
    print(f" AUTHOR: {'; '.join(authors)}")
    print(f"  TITLE: {title}")


# ============================================================
# Команды
# ============================================================

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
        stats, authors, title = lib_bgen.stat(Path(args.path))
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    t_w = sum(a for a, _ in stats.values())
    t_c = sum(b for _, b in stats.values())

    print_cfg_stat_check_line("long")
    print_cfg_stat_check_title(authors, title)
    print_cfg_stat_check_line("long")

    print("  CHARS |  WORDS |  C/W | FILE")
    print("--------|--------|------|--------------")
    print(f"{t_c:>7} | {t_w:>6} | {t_c/t_w:>4.1f} | {len(stats)} file(s)")
    print("--------|--------|------|--------------")
    for file_name, (words, chars) in stats.items():
        print(f"{chars:>7} | {words:>6} | {chars/words:>4.1f} | {str(file_name)}")

    print_cfg_stat_check_line("long")


def cmd_cfg(args):
    try:
        config, authors, title = lib_bgen.cfg(Path(args.path))
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    config_str = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print_cfg_stat_check_line("long")
    print_cfg_stat_check_title(authors, title)
    print_cfg_stat_check_line("long")
    print("CONFIG:")
    print_cfg_stat_check_line("short")
    print(f"{config_str}")
    print_cfg_stat_check_line("long")


def cmd_check(args):
    try:
        warns, authors, title = lib_bgen.check(Path(args.path), list_rules=args.list, rules_ids=args.only)
    except lib_bgen.BgenError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    desc_indent = "   "

    print_cfg_stat_check_line("long")
    print_cfg_stat_check_title(authors, title)
    print_cfg_stat_check_line("long")
    for id, (pat, desc, w) in warns.items():
        print(f" RULE {id:03d}: \"{pat}\"")
        print(desc_indent + desc.replace("\n", "\n" + desc_indent))
        print_cfg_stat_check_line("short")
        for line_n, file, line in w:
            print(f"   [{line_n}:{file}]:")
            print(f"{line}")
        print_cfg_stat_check_line("long")


# ============================================================

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

    # book src checks by given rules
    p_check = sub.add_parser("check", help="проверить исходники проекта по предоставленным правилам")
    p_check.add_argument("path", help="путь к проекту книги")
    p_check.add_argument(
        "--only",
        metavar="RULE_ID[,RULE_ID...]",
        help="проверить только на указанные правила",
    )
    p_check.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="вывести правила, паттерны и их описания для указанного проекта",
    )
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()


