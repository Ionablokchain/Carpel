# flux_diagnostics.py - Source-aware error messages with caret rendering.
#
# A Diagnostic carries a severity, a title, an optional primary Span pointing
# into a SourceFile, an optional hint, and zero or more secondary notes.
# Rendered output looks like:
#
#     error: expected ';'
#       --> hello.flux:6:18
#        |
#      6 |     let x = 1 + 2
#        |                  ^ expected ';' here
#        |
#        = hint: every statement must end with a semicolon
#
# The renderer never raises. If a Diagnostic has no span (e.g. an internal
# compiler error), only the title is printed.

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Span:
    """An inclusive-start, exclusive-end source range.

    Lines and columns are 1-based, matching what humans see in editors.
    A single-character span has end_line == start_line and
    end_col == start_col + 1. Spans never cross newlines in practice;
    if a token spans multiple lines, the renderer clamps to the first.
    """
    start_line: int
    start_col: int
    end_line: int = 0      # if 0, treated as start_line
    end_col: int = 0       # if 0, treated as start_col + 1

    def normalize(self) -> "Span":
        sl = self.start_line
        sc = self.start_col
        el = self.end_line or sl
        ec = self.end_col or (sc + 1)
        # Spans of zero/negative width get clamped to a single char.
        if el == sl and ec <= sc:
            ec = sc + 1
        return Span(sl, sc, el, ec)


@dataclass
class SourceFile:
    """Holds a source file's name and content so diagnostics can render
    the offending line. Construct once per compilation and pass through."""
    name: str
    source: str
    _lines: Optional[List[str]] = None

    def line(self, n: int) -> str:
        if self._lines is None:
            # Split on \n only; that's how Lexer counts lines.
            self._lines = self.source.split("\n")
        if 1 <= n <= len(self._lines):
            return self._lines[n - 1]
        return ""

    @property
    def line_count(self) -> int:
        if self._lines is None:
            self._lines = self.source.split("\n")
        return len(self._lines)


@dataclass
class Diagnostic:
    severity: str          # "error" or "warning"
    title: str
    span: Optional[Span] = None
    hint: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def render(self, source: SourceFile, *, color: bool = False) -> str:
        return _render(self, source, color=color)


# ---------- rendering ----------

# ANSI codes (only used when color=True).
_RESET  = "\x1b[0m"
_BOLD   = "\x1b[1m"
_RED    = "\x1b[31m"
_YELLOW = "\x1b[33m"
_BLUE   = "\x1b[34m"
_CYAN   = "\x1b[36m"
_DIM    = "\x1b[2m"


def _c(text: str, color_code: str, enabled: bool) -> str:
    if not enabled or not color_code:
        return text
    return f"{color_code}{text}{_RESET}"


def _render(diag: Diagnostic, source: SourceFile, *, color: bool) -> str:
    sev_color = _RED if diag.severity == "error" else _YELLOW
    head = f"{_c(diag.severity, sev_color + _BOLD, color)}: {diag.title}"

    if diag.span is None:
        # No span: emit just the title plus any hint.
        out = [head]
        if diag.hint:
            out.append(f"  = {_c('hint', _CYAN, color)}: {diag.hint}")
        for note in diag.notes:
            out.append(f"  = note: {note}")
        return "\n".join(out)

    span = diag.span.normalize()
    line_text = source.line(span.start_line)

    # Gutter width: enough to hold the line number with one space on each side.
    gutter_width = max(2, len(str(span.start_line)) + 1)
    blank_gutter = " " * gutter_width + "|"
    line_gutter = f" {span.start_line:>{gutter_width - 1}} |"
    file_arrow = "-->"

    # Caret span: clamp to the visible portion of the line.
    line_len = len(line_text)
    caret_start = max(1, span.start_col)
    if span.end_line == span.start_line:
        caret_end = min(line_len + 1, span.end_col)
    else:
        caret_end = line_len + 1
    if caret_end <= caret_start:
        caret_end = caret_start + 1
    caret_width = caret_end - caret_start

    pad = " " * (caret_start - 1)
    carets = "^" * caret_width
    caret_line = (
        f"{' ' * gutter_width}| {pad}{_c(carets, sev_color + _BOLD, color)}"
    )
    if diag.hint:
        caret_line += f" {_c(diag.hint, sev_color, color)}"

    out = [
        head,
        f"{' ' * (gutter_width - 1)}{_c(file_arrow, _BLUE, color)} "
        f"{source.name}:{span.start_line}:{span.start_col}",
        blank_gutter,
        f"{line_gutter} {line_text}",
        caret_line,
    ]
    for note in diag.notes:
        out.append(f"{blank_gutter}")
        out.append(f"{' ' * gutter_width}= note: {note}")
    return "\n".join(out)


# ---------- compiler-side exceptions carrying diagnostics ----------

class CarpelDiagnosticError(Exception):
    """Raised by lexer/parser/etc. when an error has source location.

    The compiler driver catches these, renders them with the SourceFile,
    and exits cleanly. Constructors elsewhere should always pass a Span
    when one is available."""

    def __init__(self, title: str, span: Optional[Span] = None,
                 hint: Optional[str] = None, notes: Optional[List[str]] = None):
        super().__init__(title)
        self.diagnostic = Diagnostic(
            severity="error",
            title=title,
            span=span,
            hint=hint,
            notes=list(notes or []),
        )
