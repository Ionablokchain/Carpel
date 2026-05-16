# test_parser.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer
from parser import Parser
from diagnostics import CarpelDiagnosticError
from ast_nodes import (
    FunctionDecl, StructDecl, Let, Assign, IfNode, WhileNode, ReturnNode,
    BinOp, UnaryOp, Call, StructLiteral, FieldAccess, IntLiteral,
    StringLiteral, BoolLiteral, Identifier, PrintlnStmt, ExpressionStmt,
)


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


class TestParser(unittest.TestCase):

    def test_empty_program(self):
        prog = parse("")
        self.assertEqual(prog.declarations, [])

    def test_minimal_function(self):
        prog = parse("fn main() {}")
        self.assertEqual(len(prog.declarations), 1)
        fn = prog.declarations[0]
        self.assertIsInstance(fn, FunctionDecl)
        self.assertEqual(fn.name, "main")
        self.assertEqual(fn.params, [])

    def test_function_with_params_and_return(self):
        prog = parse("fn add(a: i64, b: i64) -> i64 { return a + b; }")
        fn = prog.declarations[0]
        self.assertEqual(len(fn.params), 2)
        self.assertEqual(fn.params[0][0], "a")
        self.assertEqual(fn.return_type.name, "i64")

    def test_struct_decl(self):
        prog = parse("struct Point { x: i64, y: i64, }")
        s = prog.declarations[0]
        self.assertIsInstance(s, StructDecl)
        self.assertEqual(s.name, "Point")
        self.assertEqual([f[0] for f in s.fields], ["x", "y"])

    def test_let_with_and_without_annotation(self):
        prog = parse("fn main() { let x = 1; let y: i64 = 2; }")
        body = prog.declarations[0].body
        self.assertIsInstance(body[0], Let)
        self.assertIsNone(body[0].declared_type)
        self.assertIsInstance(body[1], Let)
        self.assertEqual(body[1].declared_type.name, "i64")

    def test_operator_precedence(self):
        # 1 + 2 * 3 -> 1 + (2 * 3)
        prog = parse("fn main() { let r = 1 + 2 * 3; }")
        binop = prog.declarations[0].body[0].value
        self.assertIsInstance(binop, BinOp)
        self.assertEqual(binop.op, "+")
        self.assertIsInstance(binop.right, BinOp)
        self.assertEqual(binop.right.op, "*")

    def test_left_associative_subtraction(self):
        # 10 - 3 - 2 -> (10 - 3) - 2 = 5
        prog = parse("fn main() { let r = 10 - 3 - 2; }")
        outer = prog.declarations[0].body[0].value
        self.assertEqual(outer.op, "-")
        self.assertIsInstance(outer.left, BinOp)

    def test_if_else_if_chain(self):
        prog = parse(
            "fn main() {"
            "  if true { return; }"
            "  else if false { return; }"
            "  else { return; }"
            "}"
        )
        if_node = prog.declarations[0].body[0]
        self.assertEqual(len(if_node.else_branch), 1)
        self.assertIsInstance(if_node.else_branch[0], IfNode)

    def test_while(self):
        prog = parse("fn main() { while true { return; } }")
        self.assertIsInstance(prog.declarations[0].body[0], WhileNode)

    def test_function_call(self):
        prog = parse("fn f() -> i64 { return 0; } fn main() { let x = f(); }")
        let_stmt = prog.declarations[1].body[0]
        self.assertIsInstance(let_stmt.value, Call)
        self.assertEqual(let_stmt.value.callee, "f")

    def test_struct_literal(self):
        prog = parse(
            "struct P { x: i64, y: i64, } "
            "fn main() { let p = P { x: 1, y: 2 }; }"
        )
        let_stmt = prog.declarations[1].body[0]
        self.assertIsInstance(let_stmt.value, StructLiteral)
        self.assertEqual(let_stmt.value.type_name, "P")

    def test_field_access_chain(self):
        prog = parse(
            "struct A { b: i64, } "
            "fn main() { let a = A { b: 1 }; let v = a.b; }"
        )
        let_stmt = prog.declarations[1].body[1]
        self.assertIsInstance(let_stmt.value, FieldAccess)

    def test_println(self):
        prog = parse('fn main() { println!("hi {}", 42); }')
        stmt = prog.declarations[0].body[0]
        self.assertIsInstance(stmt, PrintlnStmt)
        self.assertEqual(len(stmt.args), 1)

    def test_missing_semicolon_diagnostic(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            parse("fn main() { let x = 1 }")
        d = ctx.exception.diagnostic
        self.assertIsNotNone(d.span)
        self.assertIn("';'", d.title)

    def test_top_level_let_rejected(self):
        with self.assertRaises(CarpelDiagnosticError):
            parse("let x = 1;")


if __name__ == "__main__":
    unittest.main()
