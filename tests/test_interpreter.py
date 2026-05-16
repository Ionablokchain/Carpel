# test_interpreter.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compiler"))

from lexer import Lexer
from parser import Parser
from type_checker import TypeChecker
from interpreter import (
    Interpreter, CarpelRuntimeError, make_capturing_interpreter, StructValue,
)


def run(src):
    """Type-check, run with a capturing sink, return the list of printed lines."""
    prog = Parser(Lexer(src).tokenize()).parse()
    TypeChecker().check(prog)
    interp = make_capturing_interpreter()
    interp.run(prog)
    return interp.sink.lines


class TestArithmetic(unittest.TestCase):

    def test_simple_addition(self):
        lines = run('fn main() { println!("{}", 2 + 3); }')
        self.assertEqual(lines, ["5"])

    def test_precedence(self):
        lines = run('fn main() { println!("{}", 1 + 2 * 3); }')
        self.assertEqual(lines, ["7"])

    def test_left_associative_subtraction(self):
        lines = run('fn main() { println!("{}", 10 - 3 - 2); }')
        self.assertEqual(lines, ["5"])

    def test_integer_division_truncates_toward_zero(self):
        # 7 / 2 = 3, -7 / 2 = -3 (toward zero, not toward -inf)
        lines = run('fn main() {'
                    '  println!("{}", 7 / 2);'
                    '  println!("{}", -7 / 2);'
                    '}')
        self.assertEqual(lines, ["3", "-3"])

    def test_modulo(self):
        lines = run('fn main() { println!("{}", 10 % 3); }')
        self.assertEqual(lines, ["1"])

    def test_division_by_zero_raises(self):
        with self.assertRaises(CarpelRuntimeError):
            run('fn main() { let x = 1 / 0; }')


class TestControlFlow(unittest.TestCase):

    def test_if_then(self):
        lines = run('fn main() {'
                    '  if true { println!("yes"); }'
                    '  else { println!("no"); }'
                    '}')
        self.assertEqual(lines, ["yes"])

    def test_if_else(self):
        lines = run('fn main() {'
                    '  if false { println!("yes"); }'
                    '  else { println!("no"); }'
                    '}')
        self.assertEqual(lines, ["no"])

    def test_else_if_chain(self):
        lines = run('fn main() {'
                    '  let x = 2;'
                    '  if x == 1 { println!("one"); }'
                    '  else if x == 2 { println!("two"); }'
                    '  else { println!("other"); }'
                    '}')
        self.assertEqual(lines, ["two"])

    def test_while_counts_to_three(self):
        lines = run('fn main() {'
                    '  let mut i = 0;'
                    '  while i < 3 {'
                    '    println!("{}", i);'
                    '    i = i + 1;'
                    '  }'
                    '}')
        self.assertEqual(lines, ["0", "1", "2"])


class TestLogicalShortCircuit(unittest.TestCase):

    def test_and_short_circuits(self):
        # If the right side were evaluated, division by zero would raise.
        lines = run('fn main() {'
                    '  let b = false && (1 / 0 == 0);'
                    '  println!("{}", b);'
                    '}')
        self.assertEqual(lines, ["false"])

    def test_or_short_circuits(self):
        lines = run('fn main() {'
                    '  let b = true || (1 / 0 == 0);'
                    '  println!("{}", b);'
                    '}')
        self.assertEqual(lines, ["true"])


class TestFunctions(unittest.TestCase):

    def test_function_returns_sum(self):
        lines = run(
            'fn add(a: i64, b: i64) -> i64 { return a + b; } '
            'fn main() { println!("{}", add(2, 3)); }'
        )
        self.assertEqual(lines, ["5"])

    def test_recursive_factorial(self):
        lines = run(
            'fn fact(n: i64) -> i64 {'
            '  if n <= 1 { return 1; }'
            '  return n * fact(n - 1);'
            '} '
            'fn main() { println!("{}", fact(10)); }'
        )
        self.assertEqual(lines, ["3628800"])

    def test_mutual_recursion(self):
        lines = run(
            'fn is_even(n: i64) -> bool {'
            '  if n == 0 { return true; }'
            '  return is_odd(n - 1);'
            '} '
            'fn is_odd(n: i64) -> bool {'
            '  if n == 0 { return false; }'
            '  return is_even(n - 1);'
            '} '
            'fn main() {'
            '  println!("{}", is_even(10));'
            '  println!("{}", is_odd(7));'
            '}'
        )
        self.assertEqual(lines, ["true", "true"])


class TestStructs(unittest.TestCase):

    def test_struct_construction_and_field_access(self):
        lines = run(
            "struct P { x: i64, y: i64, } "
            'fn main() {'
            '  let p = P { x: 10, y: 20 };'
            '  println!("{} {}", p.x, p.y);'
            '}'
        )
        self.assertEqual(lines, ["10 20"])

    def test_nested_struct_access(self):
        lines = run(
            "struct Inner { v: i64, } "
            "struct Outer { i: Inner, } "
            'fn main() {'
            '  let o = Outer { i: Inner { v: 99 } };'
            '  println!("{}", o.i.v);'
            '}'
        )
        self.assertEqual(lines, ["99"])

    def test_struct_passed_by_value_to_function(self):
        lines = run(
            "struct P { x: i64, y: i64, } "
            "fn sum(p: P) -> i64 { return p.x + p.y; } "
            'fn main() {'
            '  let p = P { x: 3, y: 4 };'
            '  println!("{}", sum(p));'
            '}'
        )
        self.assertEqual(lines, ["7"])


class TestPrintln(unittest.TestCase):

    def test_no_placeholders(self):
        lines = run('fn main() { println!("hello"); }')
        self.assertEqual(lines, ["hello"])

    def test_single_placeholder(self):
        lines = run('fn main() { println!("v = {}", 42); }')
        self.assertEqual(lines, ["v = 42"])

    def test_multiple_placeholders(self):
        lines = run('fn main() { println!("{} + {} = {}", 1, 2, 3); }')
        self.assertEqual(lines, ["1 + 2 = 3"])

    def test_bool_is_lowercase(self):
        lines = run('fn main() { println!("{}", true); println!("{}", false); }')
        self.assertEqual(lines, ["true", "false"])

    def test_escaped_braces(self):
        lines = run('fn main() { println!("{{x}}"); }')
        self.assertEqual(lines, ["{x}"])


if __name__ == "__main__":
    unittest.main()
