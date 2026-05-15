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


# ---------- statements ----------

@dataclass
class Let(Node):
    name: str
    name_span: Span
    declared_type: Optional[Type]              # None when omitted
    value: Node
    span: Span


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
