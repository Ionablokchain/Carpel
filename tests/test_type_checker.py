# test_type_checker.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer
from parser import Parser
from type_checker import TypeChecker, T_I64, T_BOOL, T_STRING
from diagnostics import CarpelDiagnosticError


def check(src):
    """Type-check `src`. Raises CarpelDiagnosticError on failure."""
    prog = Parser(Lexer(src).tokenize()).parse()
    TypeChecker().check(prog)


class TestValidPrograms(unittest.TestCase):

    def test_minimal_main(self):
        check("fn main() {}")

    def test_arithmetic(self):
        check("fn main() { let x: i64 = 1 + 2 * 3 - 4; }")

    def test_let_with_no_annotation_infers(self):
        check("fn main() { let x = 5; let y = x + 1; }")

    def test_bool_and_comparison(self):
        check(
            "fn main() {"
            "  let b: bool = 1 < 2;"
            "  let c = b && true;"
            "}"
        )

    def test_function_call_typechecks(self):
        check(
            "fn add(a: i64, b: i64) -> i64 { return a + b; } "
            "fn main() { let x: i64 = add(1, 2); }"
        )

    def test_recursive_function(self):
        check(
            "fn fact(n: i64) -> i64 {"
            "  if n <= 1 { return 1; }"
            "  return n * fact(n - 1);"
            "} "
            "fn main() { let x = fact(5); }"
        )

    def test_struct_construction_and_access(self):
        check(
            "struct P { x: i64, y: i64, } "
            "fn main() {"
            "  let p = P { x: 1, y: 2 };"
            "  let v: i64 = p.x;"
            "}"
        )

    def test_nested_struct(self):
        check(
            "struct Inner { v: i64, } "
            "struct Outer { i: Inner, } "
            "fn main() {"
            "  let o = Outer { i: Inner { v: 7 } };"
            "  let x: i64 = o.i.v;"
            "}"
        )


class TestRejections(unittest.TestCase):

    def _expect(self, src, fragment):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(src)
        self.assertIn(fragment, ctx.exception.diagnostic.title.lower())

    def test_int_assigned_to_string_annotation(self):
        self._expect(
            'fn main() { let x: string = 42; }',
            "type mismatch",
        )

    def test_int_plus_string(self):
        self._expect(
            'fn main() { let r = 1 + "x"; }',
            "i64",
        )

    def test_string_plus_string_not_allowed_v01(self):
        self._expect(
            'fn main() { let r = "a" + "b"; }',
            "i64",
        )

    def test_bool_arithmetic_rejected(self):
        self._expect(
            "fn main() { let r = true + false; }",
            "i64",
        )

    def test_if_non_bool_condition(self):
        self._expect(
            "fn main() { if 1 { return; } }",
            "if condition must be bool",
        )

    def test_while_non_bool_condition(self):
        self._expect(
            'fn main() { while "x" { return; } }',
            "while condition must be bool",
        )

    def test_return_type_mismatch(self):
        self._expect(
            'fn f() -> i64 { return "abc"; } fn main() {}',
            "return type mismatch",
        )

    def test_missing_return_on_non_unit(self):
        self._expect(
            "fn f() -> i64 { let x = 5; } fn main() {}",
            "must return i64 on all paths",
        )

    def test_undeclared_variable(self):
        self._expect(
            "fn main() { let x = y; }",
            "undefined variable",
        )

    def test_undeclared_function(self):
        self._expect(
            "fn main() { let x = noSuch(1); }",
            "undefined function",
        )

    def test_wrong_arg_count(self):
        self._expect(
            "fn f(a: i64) -> i64 { return a; } "
            "fn main() { let x = f(1, 2); }",
            "expects 1 arguments",
        )

    def test_wrong_arg_type(self):
        self._expect(
            'fn f(a: i64) -> i64 { return a; } '
            'fn main() { let x = f("hi"); }',
            "argument 1 to 'f'",
        )

    def test_struct_missing_field(self):
        self._expect(
            "struct P { x: i64, y: i64, } "
            "fn main() { let p = P { x: 1 }; }",
            "missing field 'y'",
        )

    def test_struct_extra_field(self):
        self._expect(
            "struct P { x: i64, } "
            "fn main() { let p = P { x: 1, z: 2 }; }",
            "no field 'z'",
        )

    def test_struct_wrong_field_type(self):
        self._expect(
            'struct P { x: i64, } '
            'fn main() { let p = P { x: "hi" }; }',
            "field 'x' of 'p'",
        )

    def test_field_access_on_non_struct(self):
        self._expect(
            "fn main() { let x = 1; let y = x.foo; }",
            "field access requires a struct",
        )

    def test_unknown_field(self):
        self._expect(
            "struct P { x: i64, } "
            "fn main() { let p = P { x: 1 }; let q = p.y; }",
            "no field 'y'",
        )

    def test_struct_equality_rejected(self):
        self._expect(
            "struct P { x: i64, } "
            "fn main() {"
            "  let a = P { x: 1 };"
            "  let b = P { x: 1 };"
            "  let eq = a == b;"
            "}",
            "cannot compare struct",
        )

    def test_unknown_type_annotation(self):
        self._expect(
            "fn main() { let x: NoSuch = 1; }",
            "unknown type",
        )

    def test_duplicate_struct(self):
        self._expect(
            "struct P { x: i64, } struct P { y: i64, } fn main() {}",
            "already declared",
        )

    def test_duplicate_function(self):
        self._expect(
            "fn f() {} fn f() {} fn main() {}",
            "already declared",
        )

    def test_main_must_exist(self):
        self._expect("fn helper() {}", "no 'main'")

    def test_main_must_have_no_params(self):
        self._expect("fn main(x: i64) {}", "no parameters")


class TestScoping(unittest.TestCase):

    def test_variable_does_not_leak_out_of_block(self):
        with self.assertRaises(CarpelDiagnosticError):
            check(
                "fn main() {"
                "  if true { let x = 1; }"
                "  let y = x;"   # x is out of scope
                "}"
            )

    def test_shadowing_in_nested_block(self):
        # Inner block can redeclare a name from an outer scope.
        check(
            "fn main() {"
            "  let x = 1;"
            "  if true { let x = 2; }"
            "}"
        )


if __name__ == "__main__":
    unittest.main()
