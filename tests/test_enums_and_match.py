# test_enums_and_match.py - Coverage for enum declarations, variant
# construction, match statements, exhaustiveness, and pattern bindings.
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer, TokenType
from parser import Parser
from type_checker import TypeChecker
from interpreter import make_capturing_interpreter, VariantValue
from diagnostics import CarpelDiagnosticError
from ast_nodes import (
    EnumDecl, EnumVariantDecl, MatchStmt, VariantConstruction,
    WildcardPattern, VariablePattern, LiteralPattern, VariantPattern,
)


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def check(src):
    prog = parse(src)
    TypeChecker().check(prog)


def run(src):
    prog = parse(src)
    TypeChecker().check(prog)
    interp = make_capturing_interpreter()
    interp.run(prog)
    return interp.sink.lines


# ---------- lexer ----------

class TestLexer(unittest.TestCase):

    def test_enum_match_keywords(self):
        toks = Lexer("enum match").tokenize()
        self.assertEqual(toks[0].type, TokenType.ENUM)
        self.assertEqual(toks[1].type, TokenType.MATCH)

    def test_double_colon(self):
        toks = Lexer("Foo::Bar").tokenize()
        self.assertEqual(toks[1].type, TokenType.COLON_COLON)

    def test_fat_arrow(self):
        toks = Lexer("x => y").tokenize()
        self.assertEqual(toks[1].type, TokenType.FAT_ARROW)

    def test_bare_underscore_is_wildcard(self):
        toks = Lexer("_").tokenize()
        self.assertEqual(toks[0].type, TokenType.UNDERSCORE)

    def test_underscore_prefix_still_ident(self):
        toks = Lexer("_x").tokenize()
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "_x")


# ---------- parser ----------

class TestParserEnums(unittest.TestCase):

    def test_unit_variant(self):
        prog = parse("enum E { A, B, } fn main() {}")
        e = prog.declarations[0]
        self.assertIsInstance(e, EnumDecl)
        self.assertEqual([v.kind for v in e.variants], ["unit", "unit"])

    def test_tuple_variant(self):
        prog = parse("enum E { A(i64), B(i64, bool), } fn main() {}")
        v = prog.declarations[0].variants
        self.assertEqual(v[0].kind, "tuple")
        self.assertEqual(len(v[0].tuple_types), 1)
        self.assertEqual(len(v[1].tuple_types), 2)

    def test_struct_variant(self):
        prog = parse(
            "enum E { Point { x: i64, y: i64 }, } fn main() {}"
        )
        v = prog.declarations[0].variants[0]
        self.assertEqual(v.kind, "struct")
        self.assertEqual([f[0] for f in v.struct_fields], ["x", "y"])

    def test_empty_enum_rejected(self):
        with self.assertRaises(CarpelDiagnosticError):
            parse("enum E { } fn main() {}")


class TestParserVariantConstruction(unittest.TestCase):

    def test_unit_construction(self):
        prog = parse("enum E { A, } fn main() { let v = E::A; }")
        let_stmt = prog.declarations[1].body[0]
        self.assertIsInstance(let_stmt.value, VariantConstruction)
        self.assertEqual(let_stmt.value.kind, "unit")

    def test_tuple_construction(self):
        prog = parse(
            "enum E { A(i64), } fn main() { let v = E::A(42); }"
        )
        v = prog.declarations[1].body[0].value
        self.assertEqual(v.kind, "tuple")
        self.assertEqual(len(v.tuple_args), 1)

    def test_struct_construction(self):
        prog = parse(
            "enum E { A { x: i64 }, } fn main() { let v = E::A { x: 1 }; }"
        )
        v = prog.declarations[1].body[0].value
        self.assertEqual(v.kind, "struct")


class TestParserMatch(unittest.TestCase):

    def test_match_with_arms(self):
        prog = parse(
            "enum E { A, B, } "
            "fn main() {"
            "  let v = E::A;"
            "  match v {"
            "    E::A => { return; },"
            "    E::B => { return; },"
            "  }"
            "}"
        )
        match_stmt = prog.declarations[1].body[1]
        self.assertIsInstance(match_stmt, MatchStmt)
        self.assertEqual(len(match_stmt.arms), 2)

    def test_match_pattern_kinds(self):
        prog = parse(
            "enum E { A(i64), } "
            "fn main() {"
            "  let v = E::A(1);"
            "  match v {"
            "    E::A(x) => { return; },"
            "    _ => { return; },"
            "  }"
            "}"
        )
        arms = prog.declarations[1].body[1].arms
        self.assertIsInstance(arms[0].pattern, VariantPattern)
        self.assertIsInstance(arms[1].pattern, WildcardPattern)

    def test_struct_variant_shorthand(self):
        # `E::A { x }` is short for `E::A { x: x }`.
        prog = parse(
            "enum E { A { x: i64 }, } "
            "fn main() {"
            "  let v = E::A { x: 5 };"
            "  match v {"
            "    E::A { x } => { return; },"
            "  }"
            "}"
        )
        pat = prog.declarations[1].body[1].arms[0].pattern
        self.assertIsInstance(pat, VariantPattern)
        # The shorthand desugars to a VariablePattern named "x".
        fname, sub_pat, _ = pat.struct_sub[0]
        self.assertEqual(fname, "x")
        self.assertIsInstance(sub_pat, VariablePattern)
        self.assertEqual(sub_pat.name, "x")

    def test_literal_patterns(self):
        prog = parse(
            'fn main() {'
            '  let x = 3;'
            '  match x {'
            '    1 => { return; },'
            '    -2 => { return; },'
            '    _ => { return; },'
            '  }'
            '}'
        )
        arms = prog.declarations[0].body[1].arms
        self.assertIsInstance(arms[0].pattern, LiteralPattern)
        self.assertEqual(arms[0].pattern.value, 1)
        self.assertEqual(arms[1].pattern.value, -2)


# ---------- type checker ----------

class TestTypeCheckerEnums(unittest.TestCase):

    def test_well_formed_enum_and_construction(self):
        check(
            "enum E { A(i64), B, } "
            "fn main() { let x = E::A(1); let y = E::B; }"
        )

    def test_unknown_enum(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check("fn main() { let v = E::A; }")
        self.assertIn("unknown enum", ctx.exception.diagnostic.title)

    def test_unknown_variant(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum E { A, } "
                "fn main() { let v = E::B; }"
            )
        self.assertIn("no variant", ctx.exception.diagnostic.title)

    def test_wrong_payload_type(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                'enum E { A(i64), } '
                'fn main() { let v = E::A("x"); }'
            )
        self.assertIn("expected i64", ctx.exception.diagnostic.title)

    def test_unit_variant_used_as_tuple(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum E { A, } "
                "fn main() { let v = E::A(1); }"
            )
        self.assertIn("declared as unit", ctx.exception.diagnostic.title)

    def test_struct_variant_missing_field(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum E { A { x: i64, y: i64 }, } "
                "fn main() { let v = E::A { x: 1 }; }"
            )
        self.assertIn("missing field 'y'", ctx.exception.diagnostic.title)

    def test_duplicate_variant(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check("enum E { A, A, } fn main() {}")
        self.assertIn("duplicate variant", ctx.exception.diagnostic.title)

    def test_enum_name_conflicts_with_struct(self):
        with self.assertRaises(CarpelDiagnosticError):
            check("struct X { x: i64, } enum X { A, } fn main() {}")


class TestExhaustiveness(unittest.TestCase):

    def test_exhaustive_passes(self):
        check(
            "enum Color { Red, Green, Blue, } "
            "fn main() {"
            "  let c = Color::Red;"
            "  match c {"
            "    Color::Red   => {},"
            "    Color::Green => {},"
            "    Color::Blue  => {},"
            "  }"
            "}"
        )

    def test_non_exhaustive_rejected(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum Color { Red, Green, Blue, } "
                "fn main() {"
                "  let c = Color::Red;"
                "  match c {"
                "    Color::Red   => {},"
                "    Color::Green => {},"
                "  }"
                "}"
            )
        self.assertIn("non-exhaustive", ctx.exception.diagnostic.title)
        self.assertIn("Blue", ctx.exception.diagnostic.title)

    def test_catchall_makes_exhaustive(self):
        check(
            "enum Color { Red, Green, Blue, } "
            "fn main() {"
            "  let c = Color::Red;"
            "  match c {"
            "    Color::Red => {},"
            "    _ => {},"
            "  }"
            "}"
        )

    def test_unreachable_arm_after_catchall(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "enum E { A, B, } "
                "fn main() {"
                "  let v = E::A;"
                "  match v {"
                "    _ => {},"
                "    E::A => {},"
                "  }"
                "}"
            )
        self.assertIn("unreachable", ctx.exception.diagnostic.title)

    def test_match_on_i64_requires_catchall(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            check(
                "fn main() {"
                "  let x = 5;"
                "  match x {"
                "    1 => {},"
                "    2 => {},"
                "  }"
                "}"
            )
        self.assertIn("non-exhaustive", ctx.exception.diagnostic.title)


class TestPatternTypechecking(unittest.TestCase):

    def test_pattern_type_mismatch(self):
        # Pattern for wrong enum
        with self.assertRaises(CarpelDiagnosticError):
            check(
                "enum A { X, } enum B { Y, } "
                "fn main() {"
                "  let v = A::X;"
                "  match v {"
                "    B::Y => {},"
                "    _ => {},"
                "  }"
                "}"
            )

    def test_literal_pattern_wrong_type(self):
        with self.assertRaises(CarpelDiagnosticError):
            check(
                "enum E { A, } "
                "fn main() {"
                "  let v = E::A;"
                "  match v {"
                "    42 => {},"
                "    _  => {},"
                "  }"
                "}"
            )

    def test_pattern_binding_visible_in_arm_body(self):
        # Just verifying it type-checks; runtime tests cover the actual value.
        check(
            "enum E { A(i64), } "
            "fn main() {"
            "  let v = E::A(7);"
            "  match v {"
            "    E::A(n) => { let x: i64 = n; },"
            "  }"
            "}"
        )

    def test_pattern_binding_not_visible_outside_arm(self):
        with self.assertRaises(CarpelDiagnosticError):
            check(
                "enum E { A(i64), } "
                "fn main() {"
                "  let v = E::A(1);"
                "  match v {"
                "    E::A(n) => {},"
                "  }"
                "  let y = n;"     # n is out of scope here
                "}"
            )


# ---------- interpreter ----------

class TestInterpreterRuntime(unittest.TestCase):

    def test_unit_variant_round_trip(self):
        lines = run(
            'enum E { A, B, } '
            'fn main() {'
            '  let v = E::A;'
            '  match v {'
            '    E::A => { println!("a"); },'
            '    E::B => { println!("b"); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["a"])

    def test_tuple_variant_binding(self):
        lines = run(
            'enum E { Some(i64), None, } '
            'fn main() {'
            '  let v = E::Some(42);'
            '  match v {'
            '    E::Some(x) => { println!("got {}", x); },'
            '    E::None    => { println!("nothing"); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["got 42"])

    def test_struct_variant_binding(self):
        lines = run(
            'enum Shape { Rect { w: i64, h: i64 }, } '
            'fn main() {'
            '  let r = Shape::Rect { w: 3, h: 4 };'
            '  match r {'
            '    Shape::Rect { w, h } => { println!("{}", w * h); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["12"])

    def test_struct_variant_binding_with_rename(self):
        lines = run(
            'enum Shape { Rect { w: i64, h: i64 }, } '
            'fn main() {'
            '  let r = Shape::Rect { w: 3, h: 4 };'
            '  match r {'
            '    Shape::Rect { w: width, h: height } => {'
            '      println!("{}", width * height);'
            '    },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["12"])

    def test_literal_match_on_int(self):
        lines = run(
            'fn main() {'
            '  let x = 2;'
            '  match x {'
            '    1 => { println!("one"); },'
            '    2 => { println!("two"); },'
            '    _ => { println!("other"); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["two"])

    def test_first_matching_arm_wins(self):
        # The second arm of E::A would also match, but the first one fires.
        lines = run(
            'enum E { A(i64), } '
            'fn main() {'
            '  let v = E::A(5);'
            '  match v {'
            '    E::A(1) => { println!("one"); },'
            '    E::A(n) => { println!("other {}", n); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["other 5"])

    def test_println_renders_variant(self):
        lines = run(
            'enum E { Some(i64), None, } '
            'fn main() {'
            '  let v = E::Some(7);'
            '  println!("{}", v);'
            '  let n = E::None;'
            '  println!("{}", n);'
            '}'
        )
        self.assertEqual(lines, ["E::Some(7)", "E::None"])

    def test_variant_returned_from_function(self):
        lines = run(
            'enum Maybe { Some(i64), None, } '
            'fn lookup(x: i64) -> Maybe {'
            '  if x == 0 { return Maybe::None; }'
            '  return Maybe::Some(x * 2);'
            '} '
            'fn main() {'
            '  match lookup(3) {'
            '    Maybe::Some(v) => { println!("got {}", v); },'
            '    Maybe::None    => { println!("none"); },'
            '  }'
            '  match lookup(0) {'
            '    Maybe::Some(v) => { println!("got {}", v); },'
            '    Maybe::None    => { println!("none"); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["got 6", "none"])

    def test_nested_variant_pattern(self):
        # Pattern matching on a value that contains another variant.
        lines = run(
            'enum Inner { I(i64), Z, } '
            'enum Outer { O(Inner), } '
            'fn main() {'
            '  let v = Outer::O(Inner::I(11));'
            '  match v {'
            '    Outer::O(Inner::I(n)) => { println!("n={}", n); },'
            '    Outer::O(Inner::Z)    => { println!("zero"); },'
            '  }'
            '}'
        )
        self.assertEqual(lines, ["n=11"])


if __name__ == "__main__":
    unittest.main()
