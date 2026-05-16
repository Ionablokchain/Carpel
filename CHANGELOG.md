# Changelog

## [0.3.0] — Mutability enforcement

`let mut` finally means something. In v0.1 and v0.2 the keyword was
parsed but ignored at type-check time; this release makes it the only
way to opt in to reassignment, and it propagates through field
assignment and pattern bindings as well.

### Added

- **Immutability by default for `let`.** Reassigning a binding that was
  declared without `mut` is a static error. The error message includes
  a note pointing to the original declaration:

  ```
  error: cannot assign to variable of immutable binding 'x'
    --> file.cp:4:7
     |
   4 |     x = 6;
     |       ^ declare 'x' with `let mut` instead of `let`
     |
     = note: 'x' was declared as immutable (at line 3, column 9)
  ```

- **Field assignment requires a mutable root.** Writing `p.x = 5;` is
  rejected unless `p` was declared with `let mut`. The rule walks
  field-access chains: `outer.inner.value = 5;` requires `outer` itself
  to be mutable. (Per-field mutability granularity is not modeled in
  v0.3.)

- **Function parameters are immutable.** Reassigning a parameter inside
  its function body is a static error. Carpel does not (yet) accept
  `mut x: i64` in parameter position.

- **Pattern bindings are immutable.** A variable pattern in a `match`
  arm (`Maybe::Some(v) => { ... }`) binds `v` immutably. Mutating `v`
  inside the arm body is a static error.

- A new `Binding` type in the type checker carries `(type, is_mut,
  decl_span)` per scope entry, replacing the previous bare `CarpelType`.
  This is what powers the precise "declared here" notes.

- **New example:** `mutability.cp` demonstrates a counter struct
  threaded through a `while` loop using `let mut` for both the loop
  variable and the struct binding, then reassigning the binding to a
  fresh value.

- **14 new tests** covering: rejection of plain `let` reassignment,
  acceptance with `mut`, type checking still applies to reassignments,
  parameter immutability (both rejection and read-only access),
  field-assignment rules including nested field chains, mutability of
  pattern bindings, error-message detail (declaration location,
  helpful hint), and end-to-end execution of mutable counter loops and
  struct-field updates.

### Changed

- The "What v0.X does not have" list in the language reference drops
  "mutability enforcement at compile time" — that's now a feature.

## [0.2.0] — Enums and pattern matching

This release adds the single biggest piece of expressiveness a small
typed language is usually missing: sum types and `match`. The shape of
the change is small in the surface syntax but reaches into every layer
of the compiler.

### Added

- **`enum` declarations** with three kinds of variants:
  - **Unit:** `North`
  - **Tuple:** `Some(i64)`
  - **Struct:** `Circle { radius: i64 }`

  All three coexist within a single enum. Empty enums are rejected at
  parse time.

- **Variant construction** with the same three forms:
  `Direction::North`, `Maybe::Some(42)`, `Shape::Circle { radius: 5 }`.
  The type checker verifies that the form matches the declared variant
  kind and that each argument or field has the right type.

- **`match` as a statement** with arms of the shape `pattern => { body }`.
  Pattern kinds:
  - `_` — wildcard, matches anything, binds nothing.
  - A bare identifier — variable pattern, matches anything, binds the
    value in the arm's scope.
  - A literal — `0`, `true`, `"foo"`, `-3` — matches by equality.
  - A variant pattern — `Color::Red`, `Maybe::Some(v)`,
    `Shape::Circle { radius }`. The `{ field }` shorthand binds `field`
    by name; `{ field: pat }` matches with a nested sub-pattern.

- **Exhaustiveness checking.** Matches on enum-typed scrutinees must
  cover every variant or include a catchall (`_` or a variable pattern).
  Matches on non-enum scrutinees (e.g. `i64`) require a catchall, since
  the checker can't enumerate all values.

- **Unreachable-arm detection.** An arm placed after a catchall is
  rejected at compile time with a hint to remove or reorder it.

- **Nested patterns.** Sub-patterns inside variant patterns are checked
  recursively, including binding collisions and type mismatches.

- **`VariantValue`** runtime type that round-trips through `println!`
  in a human-readable form (`Color::Red`, `Maybe::Some(3)`,
  `Shape::Circle { radius: 5 }`).

- **New examples:** `maybe.cp` (option-style divide), `shapes.cp`
  (Circle/Rectangle/Nothing area), `state_machine.cp` (a tiny traffic
  light driven by a function returning the next state).

- **42 new tests** covering the lexer (new tokens), the parser (all
  three variant forms, all four pattern forms, the `{ field }`
  shorthand), the type checker (variant-kind mismatches, exhaustiveness
  in both directions, unreachable arms, nested pattern bindings,
  literal pattern type matching), and the interpreter (round-trip
  construction and matching, binding visibility scoped to the arm,
  first-arm-wins precedence, formatting in `println!`).

### Changed

- The top-level declaration error now lists `enum` alongside `fn` and
  `struct` in its hint.
- Type names registered by structs and enums share a single namespace:
  declaring both `struct Foo` and `enum Foo` is a hard error.

## [0.1.0] — A language that runs

This is the first version of Carpel that actually exists as code. The
previous "release" was 1800 lines of design documentation with no
compiler, no parser, no runtime. This version replaces all of that
with ~2300 lines of Python that compile and run small Carpel programs.

### Added

- **Lexer** with full token-span tracking (start and end line/column).
  Recognizes keywords, primitive type names, integers, strings with
  escapes, multi-character operators, and `println!` as a distinct
  token.
- **Parser** (recursive descent with Pratt-style expression parsing)
  producing an AST whose every node carries enough spans to enable
  precise error reporting.
- **Type checker** with four-pass structure: collect struct names,
  resolve struct fields, collect function signatures, then check
  bodies. Verifies primitive arithmetic and comparison rules, function
  arity and argument types, struct construction completeness, field
  access, scoping, and return-on-all-paths for non-unit functions.
- **Tree-walking interpreter** that runs type-checked programs. Handles
  arithmetic with integer-division semantics, short-circuiting `&&`
  and `||`, mutual recursion, struct values passed by value, and
  `println!` with `{}` placeholders and double-brace escapes.
- **Diagnostics** with caret-rendered error messages, optional ANSI
  color (auto-detected, respects `NO_COLOR`), inline hints, and notes.
  Every error from the lexer, parser, and type checker carries a
  precise source span.
- **CLI** (`carpelc`) with `--check`, `--run`, and `--no-color` flags.
- **Examples:** `hello.cp`, `factorial.cp`, `fizzbuzz.cp`, `structs.cp`.
- **Test suite** of 90 tests across lexer, parser, type checker,
  interpreter, end-to-end example runs, and rendered diagnostic output.
  Runs in under 20 milliseconds.

### Not in this version (intentionally)

- Generics, traits, lifetimes, references.
- Pattern matching, sum types, enums.
- Arrays, vectors, slices, iterators.
- Closures or higher-order functions.
- Modules, imports, multi-file programs.
- LLVM backend, bytecode compilation, async.
- The arena / region-inference / pin model described in the original
  design docs. v0.1 deliberately drops the parts that promised more
  than a single implementation can deliver.
