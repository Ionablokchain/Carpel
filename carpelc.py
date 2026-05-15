# parser.py - Recursive-descent parser for Carpel
from typing import List, Optional, Tuple

from ast_nodes import (
    Program, FunctionDecl, StructDecl, Type,
    Let, Assign, IfNode, WhileNode, ReturnNode, ExpressionStmt, PrintlnStmt,
    Identifier, IntLiteral, StringLiteral, BoolLiteral,
    BinOp, UnaryOp, Call, StructLiteral, FieldAccess, Node,
)
from diagnostics import Span, CarpelDiagnosticError
from lexer import Token, TokenType


class ParseError(CarpelDiagnosticError):
    pass


# precedence levels
PREC_NONE       = 0
PREC_OR         = 1
PREC_AND        = 2
PREC_EQUALITY   = 3
PREC_COMPARISON = 4
PREC_TERM       = 5
PREC_FACTOR     = 6


_BINARY_PREC = {
    TokenType.OR:      PREC_OR,
    TokenType.AND:     PREC_AND,
    TokenType.EQ:      PREC_EQUALITY,
    TokenType.NEQ:     PREC_EQUALITY,
    TokenType.LT:      PREC_COMPARISON,
    TokenType.GT:      PREC_COMPARISON,
    TokenType.LE:      PREC_COMPARISON,
    TokenType.GE:      PREC_COMPARISON,
    TokenType.PLUS:    PREC_TERM,
    TokenType.MINUS:   PREC_TERM,
    TokenType.STAR:    PREC_FACTOR,
    TokenType.SLASH:   PREC_FACTOR,
    TokenType.PERCENT: PREC_FACTOR,
}

_TYPE_TOKEN_NAMES = {
    TokenType.I64_T:    "i64",
    TokenType.BOOL_T:   "bool",
    TokenType.STRING_T: "string",
    TokenType.UNIT_T:   "unit",
}

_TOKEN_NAMES = {
    TokenType.SEMICOLON: "';'",
    TokenType.COMMA:     "','",
    TokenType.COLON:     "':'",
    TokenType.LPAREN:    "'('",
    TokenType.RPAREN:    "')'",
    TokenType.LBRACE:    "'{'",
    TokenType.RBRACE:    "'}'",
    TokenType.ARROW:     "'->'",
    TokenType.ASSIGN:    "'='",
    TokenType.IDENT:     "an identifier",
    TokenType.INTEGER:   "an integer",
    TokenType.STRING:    "a string literal",
}


def _human_token(tok: Token) -> str:
    if tok.type == TokenType.EOF:
        return "end of file"
    if tok.type == TokenType.STRING:
        return f'string literal "{tok.value}"'
    if tok.type == TokenType.INTEGER:
        return f"integer {tok.value}"
    return f"{tok.value!r}"


def _token_name(t: TokenType) -> str:
    return _TOKEN_NAMES.get(t, t.name.lower())


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # ---------- entry ----------

    def parse(self) -> Program:
        decls: List[Node] = []
        while not self._check(TokenType.EOF):
            decls.append(self._declaration())
        return Program(decls)

    def _declaration(self) -> Node:
        t = self._peek().type
        if t == TokenType.FN:
            return self._parse_function()
        if t == TokenType.STRUCT:
            return self._parse_struct()
        tok = self._peek()
        raise ParseError(
            f"expected a top-level declaration, found {_human_token(tok)}",
            span=tok.span(),
            hint="expected 'fn' or 'struct'",
        )

    # ---------- top-level ----------

    def _parse_function(self) -> FunctionDecl:
        kw = self._consume(TokenType.FN)
        name_tok = self._consume(TokenType.IDENT)
        self._consume(TokenType.LPAREN)
        params: List[Tuple[str, Type, Span]] = []
        if not self._check(TokenType.RPAREN):
            params.append(self._parse_typed_param())
            while self._match(TokenType.COMMA):
                params.append(self._parse_typed_param())
        self._consume(TokenType.RPAREN)
        # return type: -> T   (default: unit)
        if self._match(TokenType.ARROW):
            return_type = self._parse_type()
        else:
            return_type = Type("unit")
        body = self._block()
        return FunctionDecl(
            name=name_tok.value,
            name_span=name_tok.span(),
            params=params,
            return_type=return_type,
            body=body,
            span=kw.span(),
        )

    def _parse_typed_param(self) -> Tuple[str, Type, Span]:
        name_tok = self._consume(TokenType.IDENT)
        self._consume(TokenType.COLON)
        ty = self._parse_type()
        return (name_tok.value, ty, name_tok.span())

    def _parse_struct(self) -> StructDecl:
        kw = self._consume(TokenType.STRUCT)
        name_tok = self._consume(TokenType.IDENT)
        self._consume(TokenType.LBRACE)
        fields: List[Tuple[str, Type, Span]] = []
        while not self._check(TokenType.RBRACE):
            field_name = self._consume(TokenType.IDENT)
            self._consume(TokenType.COLON)
            ty = self._parse_type()
            fields.append((field_name.value, ty, field_name.span()))
            # commas are required between fields, optional after the last
            if not self._check(TokenType.RBRACE):
                self._consume(TokenType.COMMA)
        self._consume(TokenType.RBRACE)
        return StructDecl(
            name=name_tok.value,
            name_span=name_tok.span(),
            fields=fields,
            span=kw.span(),
        )

    def _parse_type(self) -> Type:
        tok = self._peek()
        if tok.type in _TYPE_TOKEN_NAMES:
            self._advance()
            return Type(_TYPE_TOKEN_NAMES[tok.type], span=tok.span())
        if tok.type == TokenType.IDENT:
            self._advance()
            return Type(tok.value, span=tok.span())
        raise ParseError(
            f"expected a type, found {_human_token(tok)}",
            span=tok.span(),
            hint="types are 'i64', 'bool', 'string', 'unit', or a struct name",
        )

    # ---------- blocks / statements ----------

    def _block(self) -> List[Node]:
        self._consume(TokenType.LBRACE)
        stmts: List[Node] = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            stmts.append(self._statement())
        self._consume(TokenType.RBRACE)
        return stmts

    def _statement(self) -> Node:
        t = self._peek().type
        if t == TokenType.LET:
            return self._parse_let()
        if t == TokenType.IF:
            return self._parse_if()
        if t == TokenType.WHILE:
            return self._parse_while()
        if t == TokenType.RETURN:
            return self._parse_return()
        if t == TokenType.PRINTLN_BANG:
            return self._parse_println()
        return self._parse_assign_or_expr_stmt()

    def _parse_let(self) -> Let:
        kw = self._consume(TokenType.LET)
        # `let mut` is accepted but mutability is not enforced in v0.1;
        # consuming it now means programs that use it can be added later
        # without re-parsing.
        self._match(TokenType.MUT)
        name_tok = self._consume(TokenType.IDENT)
        declared: Optional[Type] = None
        if self._match(TokenType.COLON):
            declared = self._parse_type()
        self._consume(TokenType.ASSIGN)
        value = self._expression()
        self._consume(TokenType.SEMICOLON)
        return Let(
            name=name_tok.value, name_span=name_tok.span(),
            declared_type=declared, value=value, span=kw.span(),
        )

    def _parse_if(self) -> IfNode:
        kw = self._consume(TokenType.IF)
        cond = self._expression()
        then_branch = self._block()
        else_branch: List[Node] = []
        if self._match(TokenType.ELSE):
            if self._check(TokenType.IF):
                else_branch = [self._parse_if()]
            else:
                else_branch = self._block()
        return IfNode(cond, then_branch, else_branch, span=kw.span())

    def _parse_while(self) -> WhileNode:
        kw = self._consume(TokenType.WHILE)
        cond = self._expression()
        body = self._block()
        return WhileNode(cond, body, span=kw.span())

    def _parse_return(self) -> ReturnNode:
        kw = self._consume(TokenType.RETURN)
        value: Optional[Node] = None
        if not self._check(TokenType.SEMICOLON):
            value = self._expression()
        self._consume(TokenType.SEMICOLON)
        return ReturnNode(value, span=kw.span())

    def _parse_println(self) -> PrintlnStmt:
        kw = self._consume(TokenType.PRINTLN_BANG)
        self._consume(TokenType.LPAREN)
        fmt = self._expression()
        args: List[Node] = []
        while self._match(TokenType.COMMA):
            args.append(self._expression())
        self._consume(TokenType.RPAREN)
        self._consume(TokenType.SEMICOLON)
        return PrintlnStmt(format=fmt, args=args, span=kw.span())

    def _parse_assign_or_expr_stmt(self) -> Node:
        # An assignment target is either `IDENT = ...` or `expr.field = ...`.
        # We parse a left-hand expression and check whether '=' follows.
        expr = self._expression()
        if self._check(TokenType.ASSIGN):
            eq = self._advance()
            value = self._expression()
            self._consume(TokenType.SEMICOLON)
            if not isinstance(expr, (Identifier, FieldAccess)):
                raise ParseError(
                    "invalid assignment target",
                    span=eq.span(),
                    hint="only variables and fields can be assigned to",
                )
            return Assign(target=expr, value=value, span=eq.span())
        self._consume(TokenType.SEMICOLON)
        return ExpressionStmt(expr)

    # ---------- expressions ----------

    def _expression(self) -> Node:
        return self._parse_precedence(PREC_OR)

    def _parse_precedence(self, min_prec: int) -> Node:
        left = self._unary()
        while True:
            tok = self._peek()
            prec = _BINARY_PREC.get(tok.type, PREC_NONE)
            if prec < min_prec:
                break
            self._advance()
            right = self._parse_precedence(prec + 1)
            left = BinOp(left, tok.value, right, op_span=tok.span())
        return left

    def _unary(self) -> Node:
        if self._check(TokenType.MINUS) or self._check(TokenType.NOT):
            op_tok = self._advance()
            operand = self._unary()
            return UnaryOp(op_tok.value, operand, op_span=op_tok.span())
        return self._postfix()

    def _postfix(self) -> Node:
        expr = self._primary()
        while True:
            if self._match(TokenType.DOT):
                fname = self._consume(TokenType.IDENT)
                expr = FieldAccess(
                    obj=expr, field=fname.value,
                    field_span=fname.span(), span=fname.span(),
                )
            elif (isinstance(expr, Identifier)
                  and self._check(TokenType.LPAREN)):
                args = self._parse_args()
                expr = Call(
                    callee=expr.name, callee_span=expr.span,
                    args=args, span=expr.span,
                )
            elif (isinstance(expr, Identifier)
                  and self._check(TokenType.LBRACE)
                  and self._is_struct_literal_start()):
                expr = self._parse_struct_literal_body(expr)
            else:
                break
        return expr

    def _is_struct_literal_start(self) -> bool:
        # Distinguish `Point { x: 1, y: 2 }` (struct literal) from
        # the block at the start of `if cond { ... }` / `while cond { ... }`.
        # The parser only calls _postfix from expression contexts, so a `{`
        # right after an identifier is always a struct literal here. Even so,
        # we require the next token to be `IDENT :` to avoid false positives
        # (e.g. `if x { ... }` would never reach here because `x` is the
        # entire condition, but being explicit is safer).
        if not self._check(TokenType.LBRACE):
            return False
        # peek into { ... }
        save = self.pos
        self._advance()
        ok = (self._check(TokenType.IDENT)
              and self._peek_at(1).type == TokenType.COLON)
        self.pos = save
        return ok

    def _parse_struct_literal_body(self, type_id: Identifier) -> StructLiteral:
        self._consume(TokenType.LBRACE)
        fields: List[Tuple[str, Node, Span]] = []
        while not self._check(TokenType.RBRACE):
            fname = self._consume(TokenType.IDENT)
            self._consume(TokenType.COLON)
            value = self._expression()
            fields.append((fname.value, value, fname.span()))
            if not self._check(TokenType.RBRACE):
                self._consume(TokenType.COMMA)
        self._consume(TokenType.RBRACE)
        return StructLiteral(
            type_name=type_id.name, type_span=type_id.span,
            fields=fields, span=type_id.span,
        )

    def _parse_args(self) -> List[Node]:
        self._consume(TokenType.LPAREN)
        args: List[Node] = []
        if not self._check(TokenType.RPAREN):
            args.append(self._expression())
            while self._match(TokenType.COMMA):
                args.append(self._expression())
        self._consume(TokenType.RPAREN)
        return args

    def _primary(self) -> Node:
        tok = self._peek()
        if tok.type == TokenType.INTEGER:
            self._advance()
            return IntLiteral(tok.value, span=tok.span())
        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(tok.value, span=tok.span())
        if tok.type == TokenType.TRUE:
            self._advance()
            return BoolLiteral(True, span=tok.span())
        if tok.type == TokenType.FALSE:
            self._advance()
            return BoolLiteral(False, span=tok.span())
        if tok.type == TokenType.IDENT:
            self._advance()
            return Identifier(tok.value, span=tok.span())
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._expression()
            self._consume(TokenType.RPAREN)
            return expr
        raise ParseError(
            f"unexpected {_human_token(tok)} where an expression was expected",
            span=tok.span(),
            hint="expected a value, an identifier, or '('",
        )

    # ---------- token utilities ----------

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _peek_at(self, offset: int) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _check(self, t: TokenType) -> bool:
        return self._peek().type == t

    def _match(self, t: TokenType) -> bool:
        if self._check(t):
            self._advance()
            return True
        return False

    def _consume(self, t: TokenType) -> Token:
        if self._check(t):
            return self._advance()
        cur = self._peek()
        expected = _token_name(t)
        # Point missing ';' at the end of the previous line, like Carpel does.
        if t == TokenType.SEMICOLON and self.pos > 0:
            prev = self.tokens[self.pos - 1]
            if prev.line != cur.line:
                col = prev.end_col or (prev.column + 1)
                span = Span(prev.line, col, prev.line, col + 1)
                raise ParseError(
                    f"expected {expected}",
                    span=span,
                    hint=f"add {expected} at the end of this line",
                )
        raise ParseError(
            f"expected {expected}, found {_human_token(cur)}",
            span=cur.span(),
            hint=f"add {expected} here",
        )
