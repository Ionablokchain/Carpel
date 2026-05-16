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
    EnumDecl, EnumVariantDecl, VariantConstruction,
    MatchStmt, MatchArm,
    WildcardPattern, VariablePattern, LiteralPattern, VariantPattern,
)


# ---------- type representations ----------

@dataclass(frozen=True)
class CarpelType:
    """Canonical, comparable type. Two types are equal iff their (kind, name)
    pairs are equal. Structural matching is intentionally not used."""
    kind: str       # "primitive" | "struct" | "enum" | "unit"
    name: str       # "i64" | "bool" | "string" | "unit" | <struct/enum name>

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


@dataclass(frozen=True)
class VariantInfo:
    name: str
    kind: str                                  # 'unit' | 'tuple' | 'struct'
    tuple_types: Tuple[CarpelType, ...] = ()
    struct_fields: Tuple[Tuple[str, CarpelType], ...] = ()

    def field_type(self, name: str) -> Optional[CarpelType]:
        for fn, ft in self.struct_fields:
            if fn == name:
                return ft
        return None


@dataclass(frozen=True)
class EnumInfo:
    name: str
    variants: Tuple[VariantInfo, ...]

    def variant(self, name: str) -> Optional[VariantInfo]:
        for v in self.variants:
            if v.name == name:
                return v
        return None


@dataclass(frozen=True)
class Binding:
    """A name in scope: its resolved type, whether it can be reassigned,
    and where it was declared (used to produce 'declared here' notes on
    mutability errors)."""
    type: CarpelType
    is_mut: bool
    decl_span: Optional[Span] = None


# ---------- the checker ----------

class TypeChecker:
    def __init__(self):
        self.structs: Dict[str, StructInfo] = {}
        self.enums: Dict[str, EnumInfo] = {}
        self.functions: Dict[str, FunctionSig] = {}
        # Scope stack of name -> Binding.
        self.scopes: List[Dict[str, Binding]] = []
        # Expected return type of the current function (None outside fn).
        self.current_return: Optional[CarpelType] = None
        # Map every expression node id() -> its inferred type.
        self.types: Dict[int, CarpelType] = {}

    # ---------- entry ----------

    def check(self, program: Program) -> None:
        # Pass 1: collect struct names so types can reference each other
        # Pass 1a: collect struct names.
        for d in program.declarations:
            if isinstance(d, StructDecl):
                if (d.name in self.structs or d.name in self.enums
                        or d.name in _PRIMITIVES):
                    raise CarpelDiagnosticError(
                        f"type '{d.name}' is already declared",
                        span=d.name_span,
                        hint="pick a different name",
                    )
                self.structs[d.name] = StructInfo(d.name, ())

        # Pass 1b: collect enum names so structs and enums can reference
        # each other in field/variant types.
        for d in program.declarations:
            if isinstance(d, EnumDecl):
                if (d.name in self.structs or d.name in self.enums
                        or d.name in _PRIMITIVES):
                    raise CarpelDiagnosticError(
                        f"type '{d.name}' is already declared",
                        span=d.name_span,
                        hint="pick a different name",
                    )
                self.enums[d.name] = EnumInfo(d.name, ())

        # Pass 2a: resolve struct fields.
        for d in program.declarations:
            if isinstance(d, StructDecl):
                self._resolve_struct(d)

        # Pass 2b: resolve enum variants.
        for d in program.declarations:
            if isinstance(d, EnumDecl):
                self._resolve_enum(d)

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

    def _resolve_enum(self, d: EnumDecl) -> None:
        variants: List[VariantInfo] = []
        seen = set()
        for v in d.variants:
            if v.name in seen:
                raise CarpelDiagnosticError(
                    f"duplicate variant '{v.name}' in enum '{d.name}'",
                    span=v.name_span,
                )
            seen.add(v.name)
            if v.kind == "tuple":
                ts = tuple(self._resolve_type(t) for t, _ in v.tuple_types)
                variants.append(VariantInfo(
                    name=v.name, kind="tuple", tuple_types=ts,
                ))
            elif v.kind == "struct":
                fields: List[Tuple[str, CarpelType]] = []
                fseen = set()
                for fname, ftype, fspan in v.struct_fields:
                    if fname in fseen:
                        raise CarpelDiagnosticError(
                            f"duplicate field '{fname}' in variant "
                            f"'{d.name}::{v.name}'",
                            span=fspan,
                        )
                    fseen.add(fname)
                    fields.append((fname, self._resolve_type(ftype)))
                variants.append(VariantInfo(
                    name=v.name, kind="struct",
                    struct_fields=tuple(fields),
                ))
            else:
                variants.append(VariantInfo(name=v.name, kind="unit"))
        self.enums[d.name] = EnumInfo(d.name, tuple(variants))

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
            # Function parameters are immutable. Carpel does not (yet) accept
            # `mut x: i64` in parameter position; reassigning a parameter is
            # a static error.
            self.scopes[0][pname] = Binding(
                type=ptype, is_mut=False, decl_span=pspan,
            )
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
            self.scopes[-1][stmt.name] = Binding(
                type=bound, is_mut=stmt.is_mut, decl_span=stmt.name_span,
            )
            return False

        if isinstance(stmt, Assign):
            self._check_assign(stmt)
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

        if isinstance(stmt, MatchStmt):
            return self._check_match(stmt)

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
            b = self._lookup(expr.name)
            if b is None:
                raise CarpelDiagnosticError(
                    f"undefined variable '{expr.name}'",
                    span=expr.span,
                )
            return b.type

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

        if isinstance(expr, VariantConstruction):
            return self._infer_variant_construction(expr)

        raise CarpelDiagnosticError(
            f"internal: unhandled expression {type(expr).__name__}",
        )

    def _infer_variant_construction(self, expr: VariantConstruction) -> CarpelType:
        einfo = self.enums.get(expr.enum_name)
        if einfo is None:
            raise CarpelDiagnosticError(
                f"unknown enum '{expr.enum_name}'",
                span=expr.enum_span,
            )
        vinfo = einfo.variant(expr.variant_name)
        if vinfo is None:
            raise CarpelDiagnosticError(
                f"enum '{expr.enum_name}' has no variant "
                f"'{expr.variant_name}'",
                span=expr.variant_span,
            )
        if vinfo.kind != expr.kind:
            raise CarpelDiagnosticError(
                f"variant '{expr.enum_name}::{expr.variant_name}' is "
                f"declared as {vinfo.kind} but used as {expr.kind}",
                span=expr.variant_span,
                hint=self._variant_form_hint(expr.enum_name, vinfo),
            )
        if vinfo.kind == "unit":
            return CarpelType("enum", expr.enum_name)
        if vinfo.kind == "tuple":
            if len(expr.tuple_args) != len(vinfo.tuple_types):
                raise CarpelDiagnosticError(
                    f"variant '{expr.enum_name}::{expr.variant_name}' expects "
                    f"{len(vinfo.tuple_types)} positional values, got "
                    f"{len(expr.tuple_args)}",
                    span=expr.variant_span,
                )
            for i, (arg, expected) in enumerate(
                    zip(expr.tuple_args, vinfo.tuple_types)):
                actual = self._infer(arg)
                if actual != expected:
                    raise CarpelDiagnosticError(
                        f"position {i + 1} of "
                        f"'{expr.enum_name}::{expr.variant_name}': "
                        f"expected {expected}, got {actual}",
                        span=getattr(arg, "span", expr.variant_span),
                    )
            return CarpelType("enum", expr.enum_name)
        # struct variant
        seen = set()
        for fname, fvalue, fspan in expr.struct_fields:
            expected = vinfo.field_type(fname)
            if expected is None:
                raise CarpelDiagnosticError(
                    f"variant '{expr.enum_name}::{expr.variant_name}' "
                    f"has no field '{fname}'",
                    span=fspan,
                )
            if fname in seen:
                raise CarpelDiagnosticError(
                    f"field '{fname}' set twice in variant construction",
                    span=fspan,
                )
            seen.add(fname)
            actual = self._infer(fvalue)
            if actual != expected:
                raise CarpelDiagnosticError(
                    f"field '{fname}' of "
                    f"'{expr.enum_name}::{expr.variant_name}': "
                    f"expected {expected}, got {actual}",
                    span=getattr(fvalue, "span", fspan),
                )
        for fname, _ in vinfo.struct_fields:
            if fname not in seen:
                raise CarpelDiagnosticError(
                    f"missing field '{fname}' in construction of "
                    f"'{expr.enum_name}::{expr.variant_name}'",
                    span=expr.variant_span,
                )
        return CarpelType("enum", expr.enum_name)

    @staticmethod
    def _variant_form_hint(enum_name: str, v: VariantInfo) -> str:
        if v.kind == "unit":
            return f"this variant takes no payload: write '{enum_name}::{v.name}'"
        if v.kind == "tuple":
            placeholders = ", ".join(str(t) for t in v.tuple_types)
            return (f"this variant takes positional values: write "
                    f"'{enum_name}::{v.name}({placeholders})'")
        return (f"this variant has named fields: write "
                f"'{enum_name}::{v.name} {{ ... }}'")

    # ---------- match + patterns ----------

    def _check_match(self, stmt: MatchStmt) -> bool:
        scrutinee_type = self._infer(stmt.scrutinee)
        # Track what's still unmatched. For exhaustiveness, we model the
        # remaining matching obligation as either:
        #   - "any value of <type>"  (string set: {'_remaining'})
        #   - "any of these variant names left"  (for enums)
        #   - covered (empty)
        # Wildcards / variable patterns close any remaining obligation.
        match_kind = scrutinee_type.kind
        remaining: set
        if match_kind == "enum":
            einfo = self.enums[scrutinee_type.name]
            remaining = {v.name for v in einfo.variants}
        else:
            # For non-enum scrutinees, we treat the obligation as "any value".
            remaining = {"_any"}

        # A wildcard / variable arm after the obligation is closed is
        # unreachable; we report that as a warning-style error to keep
        # the language minimal.
        always_returns_each_arm = True
        any_arm_returns_unconditionally = True
        saw_catchall = False
        for arm in stmt.arms:
            if saw_catchall:
                raise CarpelDiagnosticError(
                    "unreachable arm: a previous arm covered all values",
                    span=arm.span,
                    hint="remove this arm or reorder the arms",
                )
            bindings = self._check_pattern(arm.pattern, scrutinee_type)
            # Push a fresh scope for the arm body with pattern bindings.
            self.scopes.append(dict(bindings))
            arm_returns = self._check_block(arm.body)
            self.scopes.pop()
            if not arm_returns:
                any_arm_returns_unconditionally = False

            # Update the remaining-obligation set.
            if isinstance(arm.pattern, (WildcardPattern, VariablePattern)):
                remaining = set()
                saw_catchall = True
            elif (isinstance(arm.pattern, VariantPattern)
                  and match_kind == "enum"
                  and arm.pattern.enum_name == scrutinee_type.name):
                # If the variant pattern itself contains only wildcards/
                # variables (no nested literal patterns), this variant is
                # fully covered. Otherwise we conservatively keep it.
                if self._variant_pattern_is_full(arm.pattern):
                    remaining.discard(arm.pattern.variant_name)
            # Literal patterns on primitives never close the obligation.

        # Exhaustiveness check: enums require all variants to be matched
        # (or a catchall to exist).
        if match_kind == "enum" and remaining:
            missing = ", ".join(sorted(remaining))
            raise CarpelDiagnosticError(
                f"non-exhaustive match: missing variant(s) {missing}",
                span=stmt.span,
                hint="add arms for the missing variants, or a `_ => { ... }` "
                     "catchall",
            )
        if match_kind != "enum" and remaining and not saw_catchall:
            # For non-enum scrutinees, require a catchall (since we can't
            # enumerate all values).
            raise CarpelDiagnosticError(
                f"non-exhaustive match on {scrutinee_type}: no catchall arm",
                span=stmt.span,
                hint="add a `_ => { ... }` arm at the end",
            )

        # The match statement returns on every path only if every arm does.
        return any_arm_returns_unconditionally

    def _variant_pattern_is_full(self, p: VariantPattern) -> bool:
        """A variant pattern fully covers its variant if all sub-patterns are
        wildcards or variable bindings (no nested literals)."""
        if p.kind == "unit":
            return True
        if p.kind == "tuple":
            return all(isinstance(sp, (WildcardPattern, VariablePattern))
                       or (isinstance(sp, VariantPattern)
                           and self._variant_pattern_is_full(sp))
                       for sp in p.tuple_sub)
        # struct kind
        return all(isinstance(sp, (WildcardPattern, VariablePattern))
                   or (isinstance(sp, VariantPattern)
                       and self._variant_pattern_is_full(sp))
                   for _, sp, _ in p.struct_sub)

    def _check_pattern(self, pat: Node,
                       expected: CarpelType) -> Dict[str, Binding]:
        """Type-check a pattern against an expected type. Returns the set
        of variable bindings the pattern introduces. Bindings produced by
        patterns are immutable (no `mut` syntax in patterns yet)."""
        if isinstance(pat, WildcardPattern):
            return {}
        if isinstance(pat, VariablePattern):
            return {pat.name: Binding(
                type=expected, is_mut=False, decl_span=pat.span,
            )}
        if isinstance(pat, LiteralPattern):
            lit_type = _PRIMITIVES.get(pat.type_name)
            if lit_type is None or lit_type != expected:
                raise CarpelDiagnosticError(
                    f"literal pattern of type {lit_type} cannot match "
                    f"scrutinee of type {expected}",
                    span=pat.span,
                )
            return {}
        if isinstance(pat, VariantPattern):
            if expected.kind != "enum" or expected.name != pat.enum_name:
                raise CarpelDiagnosticError(
                    f"pattern '{pat.enum_name}::{pat.variant_name}' does not "
                    f"match scrutinee of type {expected}",
                    span=pat.span,
                )
            einfo = self.enums.get(pat.enum_name)
            if einfo is None:
                raise CarpelDiagnosticError(
                    f"unknown enum '{pat.enum_name}'", span=pat.span,
                )
            vinfo = einfo.variant(pat.variant_name)
            if vinfo is None:
                raise CarpelDiagnosticError(
                    f"enum '{pat.enum_name}' has no variant "
                    f"'{pat.variant_name}'",
                    span=pat.span,
                )
            if vinfo.kind != pat.kind:
                raise CarpelDiagnosticError(
                    f"variant '{pat.enum_name}::{pat.variant_name}' is "
                    f"{vinfo.kind} but the pattern is written as {pat.kind}",
                    span=pat.span,
                    hint=self._variant_form_hint(pat.enum_name, vinfo),
                )
            bindings: Dict[str, Binding] = {}
            if vinfo.kind == "tuple":
                if len(pat.tuple_sub) != len(vinfo.tuple_types):
                    raise CarpelDiagnosticError(
                        f"variant '{pat.enum_name}::{pat.variant_name}' "
                        f"has {len(vinfo.tuple_types)} positional values, "
                        f"pattern has {len(pat.tuple_sub)}",
                        span=pat.span,
                    )
                for sp, st in zip(pat.tuple_sub, vinfo.tuple_types):
                    sub_b = self._check_pattern(sp, st)
                    self._merge_bindings(bindings, sub_b, pat.span)
            elif vinfo.kind == "struct":
                seen = set()
                for fname, sp, fspan in pat.struct_sub:
                    ft = vinfo.field_type(fname)
                    if ft is None:
                        raise CarpelDiagnosticError(
                            f"variant '{pat.enum_name}::{pat.variant_name}' "
                            f"has no field '{fname}'",
                            span=fspan,
                        )
                    if fname in seen:
                        raise CarpelDiagnosticError(
                            f"field '{fname}' bound twice in pattern",
                            span=fspan,
                        )
                    seen.add(fname)
                    sub_b = self._check_pattern(sp, ft)
                    self._merge_bindings(bindings, sub_b, pat.span)
                # Allow patterns to omit fields; the omitted fields are
                # simply not bound. This matches Rust's `_..` shorthand.
            return bindings
        raise CarpelDiagnosticError(
            f"internal: unhandled pattern {type(pat).__name__}",
        )

    @staticmethod
    def _merge_bindings(dst: Dict[str, Binding],
                        src: Dict[str, Binding], span: Span) -> None:
        for k, v in src.items():
            if k in dst:
                raise CarpelDiagnosticError(
                    f"variable '{k}' bound twice in the same pattern",
                    span=span,
                )
            dst[k] = v

    def _check_assign(self, stmt: Assign) -> None:
        """Check the assignment statement `target = value;`.

        Rules:
          - If the target is a bare identifier, it must refer to a binding
            that was declared with `let mut`.
          - If the target is a field access (`obj.field = value`), the root
            object must be a mutable binding. (We do not (yet) support
            partial mutability of struct fields.)
          - The value's type must match the target's type.
        """
        value_type = self._infer(stmt.value)
        target_type = self._infer(stmt.target)
        if target_type != value_type:
            raise CarpelDiagnosticError(
                f"type mismatch in assignment: target is {target_type}, "
                f"value is {value_type}",
                span=stmt.span,
            )
        # Walk the target to the root identifier so we can check mutability.
        root = stmt.target
        path: List[str] = []
        while isinstance(root, FieldAccess):
            path.append(root.field)
            root = root.obj
        if not isinstance(root, Identifier):
            raise CarpelDiagnosticError(
                "invalid assignment target",
                span=stmt.span,
                hint="only variables and `obj.field` chains may be assigned",
            )
        binding = self._lookup(root.name)
        if binding is None:
            raise CarpelDiagnosticError(
                f"undefined variable '{root.name}'",
                span=root.span,
            )
        if not binding.is_mut:
            kind = "field" if path else "variable"
            title = (
                f"cannot assign to {kind} of immutable binding '{root.name}'"
            )
            hint = (
                f"declare '{root.name}' with `let mut` instead of `let`"
            )
            notes = []
            if binding.decl_span is not None:
                notes.append(
                    f"'{root.name}' was declared as immutable "
                    f"(at line {binding.decl_span.start_line}, "
                    f"column {binding.decl_span.start_col})"
                )
            raise CarpelDiagnosticError(
                title, span=stmt.span, hint=hint, notes=notes,
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
        if annot.name in self.enums:
            return CarpelType("enum", annot.name)
        raise CarpelDiagnosticError(
            f"unknown type '{annot.name}'",
            span=annot.span,
            hint="known types: i64, bool, string, unit, or a declared struct/enum",
        )

    def _lookup(self, name: str) -> Optional[Binding]:
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None
