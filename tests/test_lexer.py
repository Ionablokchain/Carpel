# test_lexer.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer, TokenType
from diagnostics import CarpelDiagnosticError


class TestLexer(unittest.TestCase):

    def _types(self, src):
        return [t.type for t in Lexer(src).tokenize()]

    def test_empty(self):
        toks = Lexer("").tokenize()
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.EOF)

    def test_keywords(self):
        toks = Lexer("fn struct let if else while return mut true false").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertEqual(types, [
            TokenType.FN, TokenType.STRUCT, TokenType.LET,
            TokenType.IF, TokenType.ELSE, TokenType.WHILE,
            TokenType.RETURN, TokenType.MUT, TokenType.TRUE, TokenType.FALSE,
        ])

    def test_primitive_types(self):
        toks = Lexer("i64 bool string unit").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertEqual(types, [
            TokenType.I64_T, TokenType.BOOL_T,
            TokenType.STRING_T, TokenType.UNIT_T,
        ])

    def test_println_bang(self):
        toks = Lexer("println!").tokenize()
        self.assertEqual(toks[0].type, TokenType.PRINTLN_BANG)

    def test_integers(self):
        toks = Lexer("0 1 42 100").tokenize()
        values = [t.value for t in toks[:-1]]
        self.assertEqual(values, [0, 1, 42, 100])

    def test_string_with_escapes(self):
        toks = Lexer(r'"hello\nworld\t!"').tokenize()
        self.assertEqual(toks[0].value, "hello\nworld\t!")

    def test_two_char_operators(self):
        toks = Lexer("== != <= >= && || ->").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertEqual(types, [
            TokenType.EQ, TokenType.NEQ, TokenType.LE, TokenType.GE,
            TokenType.AND, TokenType.OR, TokenType.ARROW,
        ])

    def test_line_comments_skipped(self):
        toks = Lexer("// comment\nfn x() {}").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertEqual(types[0], TokenType.FN)

    def test_unterminated_string_diagnostic(self):
        with self.assertRaises(CarpelDiagnosticError) as ctx:
            Lexer('let s = "open').tokenize()
        d = ctx.exception.diagnostic
        self.assertIsNotNone(d.span)
        self.assertIn("string", d.title.lower())

    def test_token_end_columns(self):
        toks = Lexer("foo bar").tokenize()
        self.assertEqual(toks[0].column, 1)
        self.assertEqual(toks[0].end_col, 4)
        self.assertEqual(toks[1].column, 5)
        self.assertEqual(toks[1].end_col, 8)


if __name__ == "__main__":
    unittest.main()
