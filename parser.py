# interpreter.py - Tree-walking interpreter for Carpel.
#
# The AST has already been type-checked by the time the interpreter sees
# it, so the runtime is allowed to assume things that the parser alone
# could not. For instance, BinOp(i64, i64) always means integer arithmetic
# - no need to dispatch on types.
#
# Errors from here are RuntimeError (with a plain message), not diagnostics:
# anything reachable at this stage is either an internal bug or a
# semantically valid program doing something the language can't prevent
# (e.g. division by zero).

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ast_nodes import (
    Program, FunctionDecl, StructDecl,
    Let, Assign, IfNode, WhileNode, ReturnNode, ExpressionStmt, PrintlnStmt,
    Identifier, IntLiteral, StringLiteral, BoolLiteral,
    BinOp, UnaryOp, Call, StructLiteral, FieldAccess,
    Node,
)


class CarpelRuntimeError(RuntimeError):
    pass


# A struct instance at runtime is a plain dict keyed by field name,
# wrapped so we can pretty-print it and reject structural comparison.
class StructValue:
    __slots__ = ("type_name", "fields")

    def __init__(self, type_name: str, fields: Dict[str, Any]):
        self.type_name = type_name
        self.fields = fields

    def __repr__(self) -> str:
        body = ", ".join(f"{k}: {_format(v)}" for k, v in self.fields.items())
        return f"{self.type_name} {{ {body} }}"


def _format(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    if isinstance(v, StructValue):
        return repr(v)
    return str(v)


# Sentinel used to unwind a return up to the active call frame.
class _Return(Exception):
    def __init__(self, value: Any):
        self.value = value


@dataclass
class _StdoutSink:
    """Default sink: stdout. Captured sinks accumulate lines for tests."""
    capture: bool = False
    lines: List[str] = None

    def __post_init__(self):
        if self.lines is None:
            self.lines = []

    def emit(self, text: str) -> None:
        if self.capture:
            self.lines.append(text)
        else:
            print(text)


class Interpreter:
    def __init__(self, *, sink: Optional[_StdoutSink] = None):
        self.functions: Dict[str, FunctionDecl] = {}
        self.structs: Dict[str, StructDecl] = {}
        self.scopes: List[Dict[str, Any]] = []
        self.sink = sink or _StdoutSink()

    # ---------- entry ----------

    def run(self, program: Program) -> None:
        for d in program.declarations:
            if isinstance(d, FunctionDecl):
                self.functions[d.name] = d
            elif isinstance(d, StructDecl):
                self.structs[d.name] = d
        if "main" not in self.functions:
            raise CarpelRuntimeError("no main function")
        self._call_function(self.functions["main"], [])

    # ---------- calls ----------

    def _call_function(self, fn: FunctionDecl, args: List[Any]) -> Any:
        frame: Dict[str, Any] = {}
        for (pname, _ptype, _pspan), val in zip(fn.params, args):
            frame[pname] = val
        self.scopes.append(frame)
        try:
            self._exec_block(fn.body)
            return None  # implicit unit return
        except _Return as r:
            return r.value
        finally:
            self.scopes.pop()

    # ---------- statements ----------

    def _exec_block(self, stmts: List[Node]) -> None:
        # Each block introduces its own lexical scope on top of the function
        # frame. We piggy-back scopes onto the scopes list with a sentinel
        # entry so that lookups walk inner-most first.
        self.scopes.append({})
        try:
            for s in stmts:
                self._exec(s)
        finally:
            self.scopes.pop()

    def _exec(self, stmt: Node) -> None:
        if isinstance(stmt, Let):
            value = self._eval(stmt.value)
            self.scopes[-1][stmt.name] = value
            return
        if isinstance(stmt, Assign):
            value = self._eval(stmt.value)
            self._assign_target(stmt.target, value)
            return
        if isinstance(stmt, IfNode):
            cond = self._eval(stmt.condition)
            if cond:
                self._exec_block(stmt.then_branch)
            elif stmt.else_branch:
                self._exec_block(stmt.else_branch)
            return
        if isinstance(stmt, WhileNode):
            while self._eval(stmt.condition):
                self._exec_block(stmt.body)
            return
        if isinstance(stmt, ReturnNode):
            value = self._eval(stmt.value) if stmt.value is not None else None
            raise _Return(value)
        if isinstance(stmt, ExpressionStmt):
            self._eval(stmt.expression)
            return
        if isinstance(stmt, PrintlnStmt):
            self._exec_println(stmt)
            return
        raise CarpelRuntimeError(
            f"internal: unhandled statement {type(stmt).__name__}"
        )

    def _assign_target(self, target: Node, value: Any) -> None:
        if isinstance(target, Identifier):
            for s in reversed(self.scopes):
                if target.name in s:
                    s[target.name] = value
                    return
            raise CarpelRuntimeError(
                f"internal: assignment to unbound '{target.name}'"
            )
        if isinstance(target, FieldAccess):
            obj = self._eval(target.obj)
            if not isinstance(obj, StructValue):
                raise CarpelRuntimeError(
                    "internal: field assignment to non-struct"
                )
            obj.fields[target.field] = value
            return
        raise CarpelRuntimeError(
            f"internal: cannot assign to {type(target).__name__}"
        )

    # ---------- println ----------

    def _exec_println(self, stmt: PrintlnStmt) -> None:
        # Format string supports {} placeholders, one per argument.
        # Type-checking guarantees the format is a string; we still defend
        # against mismatched arg counts (which the checker doesn't enforce).
        fmt = self._eval(stmt.format)
        args = [self._eval(a) for a in stmt.args]
        out = self._format(fmt, args)
        self.sink.emit(out)

    @staticmethod
    def _format(fmt: str, args: List[Any]) -> str:
        result = []
        i = 0
        arg_idx = 0
        while i < len(fmt):
            ch = fmt[i]
            if ch == "{" and i + 1 < len(fmt) and fmt[i + 1] == "{":
                result.append("{"); i += 2; continue
            if ch == "}" and i + 1 < len(fmt) and fmt[i + 1] == "}":
                result.append("}"); i += 2; continue
            if ch == "{" and i + 1 < len(fmt) and fmt[i + 1] == "}":
                if arg_idx >= len(args):
                    raise CarpelRuntimeError(
                        "println!: more {} placeholders than arguments"
                    )
                result.append(_format(args[arg_idx]))
                arg_idx += 1
                i += 2
                continue
            result.append(ch); i += 1
        # Extra args without placeholders are appended for convenience:
        # `println!("x", v)` prints "x v".
        while arg_idx < len(args):
            result.append(" ")
            result.append(_format(args[arg_idx]))
            arg_idx += 1
        return "".join(result)

    # ---------- expressions ----------

    def _eval(self, expr: Node) -> Any:
        if isinstance(expr, IntLiteral):    return expr.value
        if isinstance(expr, BoolLiteral):   return expr.value
        if isinstance(expr, StringLiteral): return expr.value

        if isinstance(expr, Identifier):
            for s in reversed(self.scopes):
                if expr.name in s:
                    return s[expr.name]
            raise CarpelRuntimeError(
                f"internal: '{expr.name}' not bound at runtime"
            )

        if isinstance(expr, BinOp):
            # Logical operators short-circuit.
            if expr.op == "&&":
                left = self._eval(expr.left)
                return bool(left) and bool(self._eval(expr.right))
            if expr.op == "||":
                left = self._eval(expr.left)
                return bool(left) or bool(self._eval(expr.right))
            left = self._eval(expr.left)
            right = self._eval(expr.right)
            return self._apply_binop(expr.op, left, right)

        if isinstance(expr, UnaryOp):
            v = self._eval(expr.operand)
            if expr.op == "-": return -v
            if expr.op == "!": return not v
            raise CarpelRuntimeError(f"unknown unary '{expr.op}'")

        if isinstance(expr, Call):
            fn = self.functions.get(expr.callee)
            if fn is None:
                raise CarpelRuntimeError(
                    f"internal: undefined function '{expr.callee}'"
                )
            args = [self._eval(a) for a in expr.args]
            return self._call_function(fn, args)

        if isinstance(expr, StructLiteral):
            fields: Dict[str, Any] = {}
            for fname, fvalue, _ in expr.fields:
                fields[fname] = self._eval(fvalue)
            return StructValue(expr.type_name, fields)

        if isinstance(expr, FieldAccess):
            obj = self._eval(expr.obj)
            if not isinstance(obj, StructValue):
                raise CarpelRuntimeError(
                    "internal: field access on non-struct"
                )
            return obj.fields[expr.field]

        raise CarpelRuntimeError(
            f"internal: unhandled expression {type(expr).__name__}"
        )

    @staticmethod
    def _apply_binop(op: str, a: Any, b: Any) -> Any:
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        if op == "/":
            if b == 0:
                raise CarpelRuntimeError("division by zero")
            # i64 / i64: integer division (truncate toward zero).
            return int(a / b) if (a < 0) != (b < 0) and a % b != 0 else a // b
        if op == "%":
            if b == 0:
                raise CarpelRuntimeError("modulo by zero")
            return a - (int(a / b) if (a < 0) != (b < 0) and a % b != 0
                        else a // b) * b
        if op == "==": return a == b
        if op == "!=": return a != b
        if op == "<":  return a < b
        if op == ">":  return a > b
        if op == "<=": return a <= b
        if op == ">=": return a >= b
        raise CarpelRuntimeError(f"unknown binop '{op}'")


# Convenience for tests and the driver.
def make_capturing_interpreter() -> "Interpreter":
    return Interpreter(sink=_StdoutSink(capture=True))
