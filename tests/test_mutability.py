# test_mutability.py - Mutability enforcement (let mut) tests.
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer
from parser import Parser
from type_checker import TypeChecker, Binding
from interpreter import make_capturing_interpreter
from diagnostics import CarpelDiagnosticError, SourceFile


def check(src):
    """Type-check `src`. Raises CarpelDiagnosticError on failure."""
    prog = Parser(Lexer(src).tokenize()).parse()
    TypeChecker().check(prog)


def run(src):
    prog = Parser(Lexer(src).tokenize()).parse()
    TypeChecker().check(prog)
    interp = make_capturing_interpreter()
    interp.run(prog)
    return interp.sink.lines


class TestImmutableByDefault(unittest.TestCase):

    def test_let_without_mut_rejects_reassignment(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check("fn main() { let x = 5; x = 6; }")
        self.assertIn("immutable", ctx.exception.diagnostic.title)
        self.assertIn("x", ctx.exception.diagnostic.title)

    def test_let_mut_allows_reassignment(self):
        check("fn main() { let mut x = 5; x = 6; }")

    def test_reassignment_of_same_type_required(self):
        # Even with mut, the value type must still match.
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check('fn main() { let mut x = 5; x = "hi"; }')
        self.assertIn("type mismatch", ctx.exception.diagnostic.title)


class TestFunctionParameters(unittest.TestCase):

    def test_function_param_is_immutable(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "fn f(x: i64) -> i64 { x = 5; return x; } "
                "fn main() { let r = f(1); }"
            )
        self.assertIn("immutable", ctx.exception.diagnostic.title)

    def test_function_param_can_be_read(self):
        # Reading a parameter is always fine.
        check(
            "fn f(x: i64) -> i64 { return x + 1; } "
            "fn main() { let r = f(1); }"
        )


class TestFieldAssignment(unittest.TestCase):

    def test_field_assignment_requires_mut_root(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "struct P { x: i64, y: i64, } "
                "fn main() {"
                "  let p = P { x: 1, y: 2 };"
                "  p.x = 10;"
                "}"
            )
        self.assertIn("immutable", ctx.exception.diagnostic.title)
        self.assertIn("field", ctx.exception.diagnostic.title)

    def test_field_assignment_on_mut_struct_is_ok(self):
        check(
            "struct P { x: i64, y: i64, } "
            "fn main() {"
            "  let mut p = P { x: 1, y: 2 };"
            "  p.x = 10;"
            "}"
        )

    def test_nested_field_assignment_requires_mut(self):
        # `outer.inner.x = 1;` must have `outer` declared mut.
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "struct Inner { v: i64, } "
                "struct Outer { i: Inner, } "
                "fn main() {"
                "  let o = Outer { i: Inner { v: 1 } };"
                "  o.i.v = 5;"
                "}"
            )
        self.assertIn("immutable", ctx.exception.diagnostic.title)
        # The error should point at the root binding 'o', not 'i' or 'v'.
        self.assertIn("'o'", ctx.exception.diagnostic.title)

    def test_nested_field_assignment_with_mut_root_is_ok(self):
        check(
            "struct Inner { v: i64, } "
            "struct Outer { i: Inner, } "
            "fn main() {"
            "  let mut o = Outer { i: Inner { v: 1 } };"
            "  o.i.v = 5;"
            "}"
        )


class TestPatternBindings(unittest.TestCase):

    def test_pattern_binding_is_immutable(self):
        # A variable pattern in a match arm binds immutably.
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum Maybe { Some(i64), None, } "
                "fn main() {"
                "  let m = Maybe::Some(1);"
                "  match m {"
                "    Maybe::Some(v) => { v = 99; },"
                "    Maybe::None => {},"
                "  }"
                "}"
            )
        self.assertIn("immutable", ctx.exception.diagnostic.title)


class TestErrorDetails(unittest.TestCase):

    def test_error_includes_decl_location_note(self):
        sf = SourceFile("t.cp", "fn main() {\n    let x = 5;\n    x = 6;\n}\n")
        try:
            check(sf.source)
            self.fail("expected error")
        except CarpelDiagnosticError as e:
            rendered = e.diagnostic.render(sf)
            # The note should mention the original declaration's location.
            self.assertIn("declared as immutable", rendered)
            self.assertIn("line 2", rendered)

    def test_hint_suggests_let_mut(self):
        try:
            check("fn main() { let x = 5; x = 6; }")
        except CarpelDiagnosticError as e:
            self.assertIn("let mut", e.diagnostic.hint)


class TestEndToEndExecution(unittest.TestCase):

    def test_mut_counter_loop(self):
        lines = run(
            "fn main() {"
            "  let mut i = 0;"
            "  while i < 3 { println!(\"{}\", i); i = i + 1; }"
            "}"
        )
        self.assertEqual(lines, ["0", "1", "2"])

    def test_mut_struct_field_update(self):
        lines = run(
            "struct Counter { n: i64, } "
            "fn main() {"
            "  let mut c = Counter { n: 0 };"
            "  c.n = 5;"
            "  c.n = c.n + 1;"
            "  println!(\"{}\", c.n);"
            "}"
        )
        self.assertEqual(lines, ["6"])


if __name__ == "__main__":
    unittest.main()
