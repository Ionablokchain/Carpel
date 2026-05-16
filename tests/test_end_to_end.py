# test_end_to_end.py - run every example program, verify output
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer
from parser import Parser
from type_checker import TypeChecker
from interpreter import make_capturing_interpreter
from diagnostics import SourceFile, CarpelDiagnosticError

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "examples"))


def run_file(path):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    prog = Parser(Lexer(src).tokenize()).parse()
    TypeChecker().check(prog)
    interp = make_capturing_interpreter()
    interp.run(prog)
    return interp.sink.lines


class TestExamples(unittest.TestCase):

    def test_hello(self):
        lines = run_file(os.path.join(EXAMPLES_DIR, "hello.cp"))
        self.assertEqual(lines, ["Hello from Carpel"])

    def test_factorial(self):
        lines = run_file(os.path.join(EXAMPLES_DIR, "factorial.cp"))
        self.assertEqual(lines, ["10! = 3628800"])

    def test_fizzbuzz_first_15(self):
        lines = run_file(os.path.join(EXAMPLES_DIR, "fizzbuzz.cp"))
        self.assertEqual(lines, [
            "1", "2", "Fizz", "4", "Buzz",
            "Fizz", "7", "8", "Fizz", "Buzz",
            "11", "Fizz", "13", "14", "FizzBuzz",
        ])

    def test_structs(self):
        lines = run_file(os.path.join(EXAMPLES_DIR, "structs.cp"))
        self.assertEqual(lines, ["distance_squared = 25", "area = 50"])

    def test_mutability_example(self):
        lines = run_file(os.path.join(EXAMPLES_DIR, "mutability.cp"))
        self.assertEqual(lines, [
            "tick 0: value = 1",
            "tick 1: value = 2",
            "tick 2: value = 3",
            "tick 3: value = 4",
            "tick 4: value = 5",
            "reset: value = 100, step = 10",
        ])


class TestDiagnosticRendering(unittest.TestCase):
    """Verify that the rendered error output is what a user actually sees."""

    def _render_error(self, src, filename="x.cp"):
        sf = SourceFile(filename, src)
        try:
            prog = Parser(Lexer(src).tokenize()).parse()
            TypeChecker().check(prog)
            self.fail("expected a diagnostic error")
        except CarpelDiagnosticError as e:
            return e.diagnostic.render(sf, color=False)

    def test_missing_semicolon_renders_with_caret(self):
        out = self._render_error(
            "fn main() {\n"
            "    let x = 1\n"
            "}\n"
        )
        self.assertIn("error: expected ';'", out)
        self.assertIn("x.cp:2:", out)
        self.assertIn("^", out)
        # The caret should be on the let-line, not the closing brace.
        self.assertIn("let x = 1", out)

    def test_type_mismatch_renders_with_caret(self):
        out = self._render_error(
            'fn main() {\n'
            '    let s: i64 = "abc";\n'
            '}\n'
        )
        self.assertIn("type mismatch", out)
        self.assertIn("i64", out)
        self.assertIn("string", out)

    def test_undefined_variable_renders_at_use_site(self):
        out = self._render_error(
            'fn main() {\n'
            '    let v = unknown;\n'
            '}\n'
        )
        self.assertIn("undefined variable 'unknown'", out)
        self.assertIn("x.cp:2:", out)

    def test_struct_missing_field(self):
        out = self._render_error(
            "struct P { x: i64, y: i64, }\n"
            "fn main() {\n"
            "    let p = P { x: 1 };\n"
            "}\n"
        )
        self.assertIn("missing field 'y'", out)

    def test_missing_return_renders_with_hint(self):
        out = self._render_error(
            "fn f() -> i64 { let x = 5; }\n"
            "fn main() {}\n"
        )
        self.assertIn("must return i64", out)
        self.assertIn("return", out.lower())


if __name__ == "__main__":
    unittest.main()
