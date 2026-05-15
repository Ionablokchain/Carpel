# type_checker.py - Static type checking for Carpel.
#
# This is what distinguishes Carpel from Flux. Every expression has a
# resolved type, and mismatches are reported with source spans.
#
# The type system is intentionally small:
#
#   - Primitives: i64, bool, string, unit
#   - User-declared structs (records of typed fields)
#   - Function types (for callability checks)
#
# No generics, no traits, no inference of polymorphic types. Local `let`
# bindings without an annotation get their type from the right-hand side.
# A struct type is identified by its declared name; structural equality
# is not used.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from diagnostics import Span, CarpelDiagnosticError
from ast_nodes import (
    Program, FunctionDecl, StructDecl,
    Let, Assign, IfNode, WhileNode, ReturnNode, ExpressionStmt, PrintlnStmt,
    Identifier, IntLiteral, StringLiteral, BoolLiteral,
    BinOp, UnaryOp, Call, StructLiteral, FieldAccess,
    Type as TypeAnnot, Node,
)


# ---------- type representations ----------

@dataclass(frozen=True)
class CarpelType:
    """Canonical, comparable type. Two types are equal iff their (kind, name)
    pairs are equal. Structural matching is intentionally not used."""
    kind: str       # "primitive" | "struct" | "unit"
    name: str       # "i64" | "bool" | "string" | "unit" | <struct name>

    def __str__(self) -> str:
        return self.name


T_I64    = CarpelType("primitive", "i64")
T_BOOL   = CarpelType("primitive", "bool")
T_STRING = CarpelType("primitive", "string")
T_UNIT   = CarpelType("unit", "unit")


_PRIMITIVES = {
    "i64": T_I64,
    "bool": T_BOOL,
    "string": T_STRING,
    "unit": T_UNIT,
}


@dataclass(frozen=True)
class FunctionSig:
    name: str
    params: Tuple[Tuple[str, CarpelType], ...]
    return_type: CarpelType


@dataclass(frozen=True)
class StructInfo:
    name: str
    fields: Tuple[Tuple[str, CarpelType], ...]

    def field_type(self, name: str) -> Optional[CarpelType]:
        for fn, ft in self.fields:
            if fn == name:
                return ft
        return None


# ---------- the checker ----------

class TypeChecker:
    def __init__(self):
        self.structs: Dict[str, StructInfo] = {}
        self.functions: Dict[str, FunctionSig] = {}
        # Scope stack of name -> CarpelType.
        self.scopes: List[Dict[str, CarpelType]] = []
        # Expected return type of the current function (None outside fn).
        self.current_return: Optional[CarpelType] = None
        # Map every expression node id() -> its inferred type, for later
        # use by the interpreter or any consumer that wants typed AST.
        self.types: Dict[int, CarpelType] = {}

    # ---------- entry ----------

    def check(self, program: Program) -> None:
        # Pass 1: collect struct names so types can reference each other
        # in field declarations (and so functions can reference them).
        for d in program.declarations:
            if isinstance(d, StructDecl):
                if d.name in self.structs or d.name in _PRIMITIVES:
                    raise CarpelDiagnosticError(
                        f"struct '{d.name}' is already declared",
                        span=d.name_span,
                        hint="pick a different name",
                    )
                # Insert a placeholder; the actual field types are resolved
                # in pass 2 so that struct order does not matter.
                self.structs[d.name] = StructInfo(d.name, ())

        # Pass 2: resolve struct fields now that all struct names are known.
        for d in program.declarations:
            if isinstance(d, StructDecl):
                self._resolve_struct(d)

        # Pass 3: collect function signatures so forward references work.
        for d in program.declarations:
            if isinstance(d, FunctionDecl):
                if d.name in self.functions:
                    raise CarpelDiagnosticError(
                        f"function '{d.name}' is already declared",
                        span=d.name_span,
                    )
                params = tuple(
                    (pname, self._resolve_type(ptype))
                    for pname, ptype, _ in d.params
                )
                ret = self._resolve_type(d.return_type)
                self.functions[d.name] = FunctionSig(d.name, params, ret)

        # Pass 4: check bodies.
        for d in program.declarations:
            if isinstance(d, FunctionDecl):
                self._check_function(d)

        # Carpel programs must have a main() that returns unit.
        main = self.functions.get("main")
        if main is None:
            raise CarpelDiagnosticError(
                "program has no 'main' function",
                hint="define `fn main() { ... }` somewhere",
            )
        if main.params:
            raise CarpelDiagnosticError(
                "'main' must take no parameters",
                hint="write `fn main()` with empty parens",
            )
        if main.return_type != T_UNIT:
            raise CarpelDiagnosticError(
                f"'main' must return unit, got {main.return_type}",
            )

    # ---------- declarations ----------

    def _resolve_struct(self, d: StructDecl) -> None:
        fields: List[Tuple[str, CarpelType]] = []
        seen = set()
        for fname, ftype, fspan in d.fields:
            if fname in seen:
                raise CarpelDiagnosticError(
                    f"duplicate field '{fname}' in struct '{d.name}'",
                    span=fspan,
                )
            seen.add(fname)
            fields.append((fname, self._resolve_type(ftype)))
        self.structs[d.name] = StructInfo(d.name, tuple(fields))

    def _check_function(self, d: FunctionDecl) -> None:
        sig = self.functions[d.name]
        self.current_return = sig.return_type
        self.scopes = [{}]
        for (pname, ptype), (_, _, pspan) in zip(sig.params, d.params):
            if pname in self.scopes[0]:
                raise CarpelDiagnosticError(
                    f"duplicate parameter '{pname}'",
                    span=pspan,
                )
            self.scopes[0][pname] = ptype
        always_returns = self._check_block(d.body)
        if sig.return_type != T_UNIT and not always_returns:
            raise CarpelDiagnosticError(
                f"function '{d.name}' must return {sig.return_type} "
                f"on all paths",
                span=d.name_span,
                hint="add a 'return' statement at the end",
            )
        self.current_return = None
        self.scopes = []

    # ---------- statements ----------

    def _check_block(self, stmts: List[Node]) -> bool:
        """Returns True if the block is guaranteed to return on every path."""
        self.scopes.append({})
        always_returns = False
        for stmt in stmts:
            stmt_returns = self._check_stmt(stmt)
            if stmt_returns:
                always_returns = True
                # Subsequent statements are unreachable; we still type-check
                # them for completeness, but don't change `always_returns`.
        self.scopes.pop()
        return always_returns

    def _check_stmt(self, stmt: Node) -> bool:
        if isinstance(stmt, Let):
            value_type = self._infer(stmt.value)
            if stmt.declared_type is not None:
                declared = self._resolve_type(stmt.declared_type)
                if declared != value_type:
                    raise CarpelDiagnosticError(
                        f"type mismatch: '{stmt.name}' declared as "
                        f"{declared} but initializer is {value_type}",
                        span=stmt.span,
                        hint=f"change the annotation to {value_type}, or "
                             f"convert the value",
                    )
                bound = declared
            else:
                bound = value_type
            if stmt.name in self.scopes[-1]:
                raise CarpelDiagnosticError(
                    f"variable '{stmt.name}' is already declared in this scope",
                    span=stmt.name_span,
                )
            self.scopes[-1][stmt.name] = bound
            return False

        if isinstance(stmt, Assign):
            value_type = self._infer(stmt.value)
            target_type = self._infer(stmt.target)
            if target_type != value_type:
                raise CarpelDiagnosticError(
                    f"type mismatch in assignment: target is {target_type}, "
                    f"value is {value_type}",
                    span=stmt.span,
                )
            return False

        if isinstance(stmt, IfNode):
            cond_type = self._infer(stmt.condition)
            if cond_type != T_BOOL:
                raise CarpelDiagnosticError(
                    f"if condition must be bool, got {cond_type}",
                    span=getattr(stmt.condition, "span", stmt.span),
                )
            then_returns = self._check_block(stmt.then_branch)
            if stmt.else_branch:
                else_returns = self._check_block(stmt.else_branch)
                return then_returns and else_returns
            # Without an else branch, falling through is always possible.
            self._check_block([])  # no-op for symmetry
            return False

        if isinstance(stmt, WhileNode):
            cond_type = self._infer(stmt.condition)
            if cond_type != T_BOOL:
                raise CarpelDiagnosticError(
                    f"while condition must be bool, got {cond_type}",
                    span=getattr(stmt.condition, "span", stmt.span),
                )
            self._check_block(stmt.body)
            return False  # a loop body might not run

        if isinstance(stmt, ReturnNode):
            if stmt.value is None:
                if self.current_return != T_UNIT:
                    raise CarpelDiagnosticError(
                        f"return without value, but function returns "
                        f"{self.current_return}",
                        span=stmt.span,
                    )
            else:
                value_type = self._infer(stmt.value)
                if value_type != self.current_return:
                    raise CarpelDiagnosticError(
                        f"return type mismatch: function returns "
                        f"{self.current_return}, got {value_type}",
                        span=stmt.span,
                    )
            return True

        if isinstance(stmt, ExpressionStmt):
            self._infer(stmt.expression)
            return False

        if isinstance(stmt, PrintlnStmt):
            fmt_type = self._infer(stmt.format)
            if fmt_type != T_STRING:
                raise CarpelDiagnosticError(
                    f"println! format must be string, got {fmt_type}",
                    span=getattr(stmt.format, "span", stmt.span),
                )
            for a in stmt.args:
                self._infer(a)   # any type allowed; conversion happens at runtime
            return False

        raise CarpelDiagnosticError(
            f"internal: unhandled statement {type(stmt).__name__}",
        )

    # ---------- expressions ----------

    def _infer(self, expr: Node) -> CarpelType:
        t = self._infer_inner(expr)
        self.types[id(expr)] = t
        return t

    def _infer_inner(self, expr: Node) -> CarpelType:
        if isinstance(expr, IntLiteral):    return T_I64
        if isinstance(expr, BoolLiteral):   return T_BOOL
        if isinstance(expr, StringLiteral): return T_STRING

        if isinstance(expr, Identifier):
            t = self._lookup(expr.name)
            if t is None:
                raise CarpelDiagnosticError(
                    f"undefined variable '{expr.name}'",
                    span=expr.span,
                )
            return t

        if isinstance(expr, BinOp):
            lt = self._infer(expr.left)
            rt = self._infer(expr.right)
            return self._check_binop(expr.op, lt, rt, expr.op_span)

        if isinstance(expr, UnaryOp):
            ot = self._infer(expr.operand)
            if expr.op == "-":
                if ot != T_I64:
                    raise CarpelDiagnosticError(
                        f"unary '-' expects i64, got {ot}",
                        span=expr.op_span,
                    )
                return T_I64
            if expr.op == "!":
                if ot != T_BOOL:
                    raise CarpelDiagnosticError(
                        f"unary '!' expects bool, got {ot}",
                        span=expr.op_span,
                    )
                return T_BOOL
            raise CarpelDiagnosticError(
                f"unknown unary operator '{expr.op}'", span=expr.op_span,
            )

        if isinstance(expr, Call):
            sig = self.functions.get(expr.callee)
            if sig is None:
                raise CarpelDiagnosticError(
                    f"undefined function '{expr.callee}'",
                    span=expr.callee_span,
                )
            if len(expr.args) != len(sig.params):
                raise CarpelDiagnosticError(
                    f"function '{expr.callee}' expects {len(sig.params)} "
                    f"arguments, got {len(expr.args)}",
                    span=expr.span,
                )
            for i, (arg, (pname, ptype)) in enumerate(
                    zip(expr.args, sig.params)):
                at = self._infer(arg)
                if at != ptype:
                    raise CarpelDiagnosticError(
                        f"argument {i + 1} to '{expr.callee}' "
                        f"(parameter '{pname}'): expected {ptype}, got {at}",
                        span=getattr(arg, "span", expr.span),
                    )
            return sig.return_type

        if isinstance(expr, StructLiteral):
            info = self.structs.get(expr.type_name)
            if info is None:
                raise CarpelDiagnosticError(
                    f"unknown struct '{expr.type_name}'",
                    span=expr.type_span,
                )
            seen = set()
            for fname, fvalue, fspan in expr.fields:
                expected = info.field_type(fname)
                if expected is None:
                    raise CarpelDiagnosticError(
                        f"struct '{expr.type_name}' has no field '{fname}'",
                        span=fspan,
                    )
                if fname in seen:
                    raise CarpelDiagnosticError(
                        f"field '{fname}' set twice in struct literal",
                        span=fspan,
                    )
                seen.add(fname)
                actual = self._infer(fvalue)
                if actual != expected:
                    raise CarpelDiagnosticError(
                        f"field '{fname}' of '{expr.type_name}': expected "
                        f"{expected}, got {actual}",
                        span=getattr(fvalue, "span", fspan),
                    )
            for fname, _ in info.fields:
                if fname not in seen:
                    raise CarpelDiagnosticError(
                        f"missing field '{fname}' in struct literal for "
                        f"'{expr.type_name}'",
                        span=expr.span,
                    )
            return CarpelType("struct", expr.type_name)

        if isinstance(expr, FieldAccess):
            obj_type = self._infer(expr.obj)
            if obj_type.kind != "struct":
                raise CarpelDiagnosticError(
                    f"field access requires a struct, got {obj_type}",
                    span=expr.field_span,
                )
            info = self.structs.get(obj_type.name)
            if info is None:
                raise CarpelDiagnosticError(
                    f"internal: unknown struct '{obj_type.name}'",
                    span=expr.field_span,
                )
            ft = info.field_type(expr.field)
            if ft is None:
                raise CarpelDiagnosticError(
                    f"struct '{obj_type.name}' has no field '{expr.field}'",
                    span=expr.field_span,
                )
            return ft

        raise CarpelDiagnosticError(
            f"internal: unhandled expression {type(expr).__name__}",
        )

    def _check_binop(self, op: str, lt: CarpelType, rt: CarpelType,
                     op_span: Span) -> CarpelType:
        # Arithmetic
        if op in ("+", "-", "*", "/", "%"):
            if lt != T_I64 or rt != T_I64:
                raise CarpelDiagnosticError(
                    f"operator '{op}' expects (i64, i64), got ({lt}, {rt})",
                    span=op_span,
                )
            return T_I64
        # Comparisons
        if op in ("<", ">", "<=", ">="):
            if lt != T_I64 or rt != T_I64:
                raise CarpelDiagnosticError(
                    f"operator '{op}' expects (i64, i64), got ({lt}, {rt})",
                    span=op_span,
                )
            return T_BOOL
        # Equality - both sides must have the same type.
        if op in ("==", "!="):
            if lt != rt:
                raise CarpelDiagnosticError(
                    f"operator '{op}' expects matching types, got ({lt}, {rt})",
                    span=op_span,
                )
            # Disallow equality on structs in v0.1 (no structural eq yet).
            if lt.kind == "struct":
                raise CarpelDiagnosticError(
                    f"cannot compare struct values with '{op}'",
                    span=op_span,
                    hint="compare individual fields instead",
                )
            return T_BOOL
        # Logical
        if op in ("&&", "||"):
            if lt != T_BOOL or rt != T_BOOL:
                raise CarpelDiagnosticError(
                    f"operator '{op}' expects (bool, bool), got ({lt}, {rt})",
                    span=op_span,
                )
            return T_BOOL
        raise CarpelDiagnosticError(
            f"unknown binary operator '{op}'", span=op_span,
        )

    # ---------- helpers ----------

    def _resolve_type(self, annot: TypeAnnot) -> CarpelType:
        if annot.name in _PRIMITIVES:
            return _PRIMITIVES[annot.name]
        if annot.name in self.structs:
            return CarpelType("struct", annot.name)
        raise CarpelDiagnosticError(
            f"unknown type '{annot.name}'",
            span=annot.span,
            hint="known types: i64, bool, string, unit, or a declared struct",
        )

    def _lookup(self, name: str) -> Optional[CarpelType]:
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None
