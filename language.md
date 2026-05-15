#!/usr/bin/env python3
"""carpelc - The Carpel compiler / runner.

Usage:
    carpelc <file.cp> [--check] [--run] [--no-color]

  --check     Type-check only; do not run.
  --run       Type-check and execute (this is the default).
  --no-color  Disable ANSI color in error messages.
"""
import argparse
import os
import sys

from diagnostics import SourceFile, CarpelDiagnosticError
from lexer import Lexer
from parser import Parser
from type_checker import TypeChecker
from interpreter import Interpreter, CarpelRuntimeError


def _color_enabled(disabled: bool) -> bool:
    if disabled:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="carpelc")
    ap.add_argument("file")
    ap.add_argument("--check", action="store_true",
                    help="type-check only; do not run")
    ap.add_argument("--run", action="store_true",
                    help="type-check and run (default)")
    ap.add_argument("--no-color", action="store_true",
                    help="disable ANSI colors")
    args = ap.parse_args(argv)

    color = _color_enabled(args.no_color)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
        return 2

    source = SourceFile(args.file, text)

    try:
        tokens = Lexer(text).tokenize()
        program = Parser(tokens).parse()
        TypeChecker().check(program)
    except CarpelDiagnosticError as e:
        print(e.diagnostic.render(source, color=color), file=sys.stderr)
        return 1

    if args.check:
        return 0

    try:
        Interpreter().run(program)
    except CarpelRuntimeError as e:
        print(f"runtime error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
