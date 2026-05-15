# lexer.py - Tokenizer for Carpel
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Any

from diagnostics import Span, CarpelDiagnosticError


class LexerError(CarpelDiagnosticError):
    pass


class TokenType(Enum):
    # keywords
    FN          = auto()
    LET         = auto()
    MUT         = auto()
    IF          = auto()
    ELSE        = auto()
    WHILE       = auto()
    RETURN      = auto()
    STRUCT      = auto()
    TRUE        = auto()
    FALSE       = auto()

    # type keywords (also valid identifiers in expression position;
    # the parser disambiguates by context)
    I64_T       = auto()
    BOOL_T      = auto()
    STRING_T    = auto()
    UNIT_T      = auto()

    # punctuation / operators
    ASSIGN      = auto()    # =
    EQ          = auto()    # ==
    NEQ         = auto()    # !=
    LT          = auto()    # <
    GT          = auto()    # >
    LE          = auto()    # <=
    GE          = auto()    # >=
    AND         = auto()    # &&
    OR          = auto()    # ||
    NOT         = auto()    # !
    PLUS        = auto()
    MINUS       = auto()
    STAR        = auto()
    SLASH       = auto()
    PERCENT     = auto()
    DOT         = auto()
    COMMA       = auto()
    COLON       = auto()
    SEMICOLON   = auto()
    ARROW       = auto()    # ->
    LPAREN      = auto()
    RPAREN      = auto()
    LBRACE      = auto()
    RBRACE      = auto()

    # literals / identifiers
    IDENT       = auto()
    INTEGER     = auto()
    STRING      = auto()
    PRINTLN_BANG = auto()   # println!  (we treat the whole sequence as one token)

    EOF         = auto()


KEYWORDS = {
    "fn":     TokenType.FN,
    "let":    TokenType.LET,
    "mut":    TokenType.MUT,
    "if":     TokenType.IF,
    "else":   TokenType.ELSE,
    "while":  TokenType.WHILE,
    "return": TokenType.RETURN,
    "struct": TokenType.STRUCT,
    "true":   TokenType.TRUE,
    "false":  TokenType.FALSE,
    "i64":    TokenType.I64_T,
    "bool":   TokenType.BOOL_T,
    "string": TokenType.STRING_T,
    "unit":   TokenType.UNIT_T,
}


@dataclass
class Token:
    type: TokenType
    value: Any
    line: int
    column: int
    end_line: int = 0
    end_col: int = 0

    def span(self) -> Span:
        return Span(self.line, self.column,
                    self.end_line or self.line,
                    self.end_col or (self.column + 1))

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:C{self.column})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.source):
            ch = self.source[self.pos]

            if ch.isspace():
                self._advance()
                continue
            if ch == "/" and self._peek(1) == "/":
                self._skip_line_comment()
                continue
            if ch.isalpha() or ch == "_":
                self._read_identifier_or_keyword()
                continue
            if ch.isdigit():
                self._read_integer()
                continue
            if ch == '"':
                self._read_string()
                continue

            if self._match2("=="):
                self._add_with_width(TokenType.EQ, "==", 2); continue
            if self._match2("!="):
                self._add_with_width(TokenType.NEQ, "!=", 2); continue
            if self._match2("<="):
                self._add_with_width(TokenType.LE, "<=", 2); continue
            if self._match2(">="):
                self._add_with_width(TokenType.GE, ">=", 2); continue
            if self._match2("&&"):
                self._add_with_width(TokenType.AND, "&&", 2); continue
            if self._match2("||"):
                self._add_with_width(TokenType.OR, "||", 2); continue
            if self._match2("->"):
                self._add_with_width(TokenType.ARROW, "->", 2); continue

            single = {
                "=": TokenType.ASSIGN, "<": TokenType.LT, ">": TokenType.GT,
                "!": TokenType.NOT, "+": TokenType.PLUS, "-": TokenType.MINUS,
                "*": TokenType.STAR, "/": TokenType.SLASH, "%": TokenType.PERCENT,
                ".": TokenType.DOT, ",": TokenType.COMMA, ":": TokenType.COLON,
                ";": TokenType.SEMICOLON,
                "(": TokenType.LPAREN, ")": TokenType.RPAREN,
                "{": TokenType.LBRACE, "}": TokenType.RBRACE,
            }
            if ch in single:
                self._add(single[ch], ch)
                self._advance()
                continue

            raise LexerError(
                f"unknown character {ch!r}",
                span=Span(self.line, self.column,
                          self.line, self.column + 1),
                hint="this character is not part of the Carpel syntax",
            )

        self._add(TokenType.EOF, None)
        return self.tokens

    # ---------- helpers ----------

    def _advance(self) -> None:
        if self.source[self.pos] == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        self.pos += 1

    def _peek(self, offset: int = 1) -> str:
        p = self.pos + offset
        return self.source[p] if p < len(self.source) else "\0"

    def _match2(self, s: str) -> bool:
        if self.pos + 1 < len(self.source) and self.source[self.pos:self.pos + 2] == s:
            self._advance(); self._advance()
            return True
        return False

    def _add(self, t: TokenType, value: Any) -> None:
        col = self.column
        self.tokens.append(Token(t, value, self.line, col, self.line, col + 1))

    def _add_with_width(self, t: TokenType, value: Any, width: int) -> None:
        end_col = self.column
        start_col = end_col - width
        self.tokens.append(Token(t, value, self.line, start_col, self.line, end_col))

    def _skip_line_comment(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            self._advance()

    def _read_identifier_or_keyword(self) -> None:
        start = self.pos
        start_col = self.column
        while self.pos < len(self.source) and (
            self.source[self.pos].isalnum() or self.source[self.pos] == "_"
        ):
            self._advance()
        text = self.source[start:self.pos]

        # Special-case `println!` - a macro-looking token treated as one.
        if text == "println" and self.pos < len(self.source) and self.source[self.pos] == "!":
            self._advance()  # consume '!'
            end_col = self.column
            self.tokens.append(Token(
                TokenType.PRINTLN_BANG, "println!",
                self.line, start_col, self.line, end_col,
            ))
            return

        tt = KEYWORDS.get(text, TokenType.IDENT)
        end_col = self.column
        self.tokens.append(Token(tt, text, self.line, start_col, self.line, end_col))

    def _read_integer(self) -> None:
        start = self.pos
        start_col = self.column
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self._advance()
        text = self.source[start:self.pos]
        end_col = self.column
        self.tokens.append(Token(
            TokenType.INTEGER, int(text),
            self.line, start_col, self.line, end_col,
        ))

    def _read_string(self) -> None:
        start_line = self.line
        start_col = self.column
        self._advance()  # opening quote
        buf = []
        while self.pos < len(self.source) and self.source[self.pos] != '"':
            ch = self.source[self.pos]
            if ch == "\\":
                self._advance()
                if self.pos >= len(self.source):
                    raise LexerError(
                        "unterminated string literal",
                        span=Span(start_line, start_col, start_line, start_col + 1),
                        hint="string opened here is never closed",
                    )
                esc = self.source[self.pos]
                buf.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(esc, esc))
                self._advance()
            else:
                buf.append(ch)
                self._advance()
        if self.pos >= len(self.source):
            raise LexerError(
                "unterminated string literal",
                span=Span(start_line, start_col, start_line, start_col + 1),
                hint="string opened here is never closed",
            )
        self._advance()  # closing quote
        end_col = self.column
        self.tokens.append(Token(
            TokenType.STRING, "".join(buf),
            start_line, start_col, self.line, end_col,
        ))
