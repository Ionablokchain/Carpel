# ast_nodes.py - AST node definitions for Carpel
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from diagnostics import Span


# ---------- types ----------

@dataclass
class Type:
    """Surface-level type as written in source. Resolved to a canonical
    runtime type by the type checker."""
    name: str                                  # 'i64' | 'bool' | 'string' | 'unit' | <user struct>
    span: Optional[Span] = None


# ---------- nodes ----------

class Node:
    pass


@dataclass
class Program(Node):
    declarations: List[Node]


# ---------- top-level declarations ----------

@dataclass
class FunctionDecl(Node):
    name: str
    name_span: Span
    params: List[Tuple[str, Type, Span]]       # (name, declared type, name-span)
    return_type: Type
    body: List[Node]
    span: Span


@dataclass
class StructDecl(Node):
    name: str
    name_span: Span
    fields: List[Tuple[str, Type, Span]]       # (name, declared type, name-span)
    span: Span


# ---------- enums and patterns ----------

@dataclass
class EnumVariantDecl(Node):
    """A single variant of an enum.

    - kind='unit'   -> no payload, e.g. `North`
    - kind='tuple'  -> positional payload, e.g. `Some(i64)`
    - kind='struct' -> named-field payload, e.g. `Circle { radius: i64 }`
    """
    name: str
    name_span: Span
    kind: str                                  # 'unit' | 'tuple' | 'struct'
    tuple_types: List[Tuple[Type, Span]] = field(default_factory=list)
    struct_fields: List[Tuple[str, Type, Span]] = field(default_factory=list)


@dataclass
class EnumDecl(Node):
    name: str
    name_span: Span
    variants: List[EnumVariantDecl]
    span: Span


# Patterns appear only in match arms. They never carry runtime state.

@dataclass
class WildcardPattern(Node):
    """The `_` pattern: matches anything, binds nothing."""
    span: Span


@dataclass
class VariablePattern(Node):
    """A bare identifier in pattern position: matches anything, binds the
    value to the identifier in the arm's scope."""
    name: str
    span: Span


@dataclass
class LiteralPattern(Node):
    """Matches by equality. Value is one of int, bool, str."""
    value: object
    type_name: str                             # 'i64' | 'bool' | 'string'
    span: Span


@dataclass
class VariantPattern(Node):
    """`EnumName::Variant`, `EnumName::Variant(p1, p2)`, or
    `EnumName::Variant { f1, f2: p }`. Sub-patterns recurse."""
    enum_name: str
    variant_name: str
    kind: str                                  # 'unit' | 'tuple' | 'struct'
    tuple_sub: List["Node"] = field(default_factory=list)        # Patterns
    struct_sub: List[Tuple[str, "Node", Span]] = field(default_factory=list)
                                               # (field-name, pattern, name-span)
    span: Span = None


@dataclass
class MatchArm(Node):
    pattern: Node
    body: List[Node]                           # block of statements
    span: Span


@dataclass
class MatchStmt(Node):
    """`match expr { arm, arm, ... }` at statement position. The body of
    each arm is a block of statements; arms do not produce a value."""
    scrutinee: Node
    arms: List[MatchArm]
    span: Span


# ---------- statements ----------

@dataclass
class Let(Node):
    name: str
    name_span: Span
    declared_type: Optional[Type]              # None when omitted
    value: Node
    span: Span
    is_mut: bool = False                       # `let mut name = ...`


@dataclass
class Assign(Node):
    target: Node                               # Identifier or FieldAccess
    value: Node
    span: Span


@dataclass
class IfNode(Node):
    condition: Node
    then_branch: List[Node]
    else_branch: List[Node] = field(default_factory=list)
    span: Optional[Span] = None


@dataclass
class WhileNode(Node):
    condition: Node
    body: List[Node]
    span: Optional[Span] = None


@dataclass
class ReturnNode(Node):
    value: Optional[Node]
    span: Span


@dataclass
class ExpressionStmt(Node):
    expression: Node
    span: Optional[Span] = None


@dataclass
class PrintlnStmt(Node):
    """println!(format_string, args...). We treat it as a statement, not
    a normal call, because it has its own typing rule (variadic) and side
    effect semantics."""
    format: Node                               # must type-check to string
    args: List[Node]
    span: Span


# ---------- expressions ----------

@dataclass
class Identifier(Node):
    name: str
    span: Span


@dataclass
class IntLiteral(Node):
    value: int
    span: Span


@dataclass
class StringLiteral(Node):
    value: str
    span: Span


@dataclass
class BoolLiteral(Node):
    value: bool
    span: Span


@dataclass
class BinOp(Node):
    left: Node
    op: str
    right: Node
    op_span: Span


@dataclass
class UnaryOp(Node):
    op: str
    operand: Node
    op_span: Span


@dataclass
class Call(Node):
    """Function call: f(args). The callee is currently restricted to a
    bare identifier; method calls are not supported in v0.1."""
    callee: str
    callee_span: Span
    args: List[Node]
    span: Span


@dataclass
class StructLiteral(Node):
    """Point { x: 1, y: 2 }"""
    type_name: str
    type_span: Span
    fields: List[Tuple[str, Node, Span]]       # (field-name, value, name-span)
    span: Span


@dataclass
class FieldAccess(Node):
    obj: Node
    field: str
    field_span: Span
    span: Span


@dataclass
class VariantConstruction(Node):
    """`EnumName::Variant`, `EnumName::Variant(args)`, or
    `EnumName::Variant { f1: v1, ... }`. The `kind` field disambiguates."""
    enum_name: str
    enum_span: Span
    variant_name: str
    variant_span: Span
    kind: str                                  # 'unit' | 'tuple' | 'struct'
    tuple_args: List[Node] = field(default_factory=list)
    struct_fields: List[Tuple[str, Node, Span]] = field(default_factory=list)
    span: Span = None
