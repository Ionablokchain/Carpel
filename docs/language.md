# Carpel Language Reference (v0.1)

This document describes Carpel as it is implemented. Where the
implementation and any earlier specification disagree, the implementation
is authoritative.

## Lexical structure

### Comments

`// line comment` runs to end of line.

### Keywords

```
fn  struct  enum  match  let  mut  if  else  while  return  true  false
i64  bool  string  unit
```

`println!` is its own keyword-like token (note the trailing `!`).
A bare `_` (single underscore) is a distinct wildcard token; identifiers
beginning with underscore (`_foo`) are still normal identifiers.

### Identifiers

`[A-Za-z_][A-Za-z0-9_]*`. Case-sensitive.

### Literals

| Form       | Type    | Notes                              |
|------------|---------|------------------------------------|
| `42`       | i64     | Signed 64-bit integer              |
| `"text"`   | string  | Escapes: `\n \t \r \" \\`           |
| `true`/`false` | bool |                                    |

Negative integers are unary minus applied to a positive literal.

### Operators and punctuation (precedence, low to high)

```
||                   (logical or, short-circuits)
&&                   (logical and, short-circuits)
== !=
< > <= >=
+ -
* / %
unary -  !
. ( )                (member access, call)
```

Additional punctuation: `::` (path separator, used in
`EnumName::Variant`), `=>` (match arm arrow), `_` (wildcard pattern).

All binary operators are left-associative.

## Types

| Type     | Notes                                          |
|----------|------------------------------------------------|
| `i64`    | Signed 64-bit integer                          |
| `bool`   | `true` or `false`                              |
| `string` | UTF-8 text                                     |
| `unit`   | The single value `()` (only the return type of void functions) |
| `<Name>` | A user-declared struct or enum                 |

There is no `null`, no `Option`, no nullable types (although a
user-defined `Maybe`-style enum works fine). There is no implicit
conversion between any types: `1 + true` is rejected at type-check time.

## Top-level declarations

### Functions

```rust
fn name(p1: Type1, p2: Type2) -> ReturnType {
    <statements>
}
```

The return type may be omitted only for functions returning `unit`. A
function whose return type is not `unit` must return on every path; the
type checker tracks this and refuses programs that fall through.

Every program must define a `main` function with no parameters and
return type `unit`.

### Structs

```rust
struct Point {
    x: i64,
    y: i64,
}
```

Structs are value types. They are passed by value to functions and
returned by value. Field access is `point.x`. There is no `mut` rule on
fields; struct values bound with `let mut` allow field assignment via
the runtime, but v0.1 does not enforce field-level mutability.

Two structs are equal iff their declared names match. Structural
equality is intentionally not supported: `a == b` on struct values is
rejected at type-check time. Compare individual fields instead.

### Enums

```rust
enum Color {
    Red,
    Green,
    Blue,
}

enum Maybe {
    Some(i64),
    None,
}

enum Shape {
    Circle { radius: i64 },
    Square { side: i64 },
    Nothing,
}
```

An enum is a tagged union: a value of an enum type is exactly one of
its declared variants, carrying the payload that variant requires.
Three variant forms are supported:

- **Unit** — no payload. Constructed as `Color::Red`.
- **Tuple** — positional payload. Constructed as `Maybe::Some(42)`.
  The argument types are checked positionally.
- **Struct** — named-field payload. Constructed as
  `Shape::Circle { radius: 5 }`. All declared fields must be set.

The three forms can coexist within a single enum (see `Shape` above).
Empty enums (no variants) are rejected at parse time.

Structs and enums share a single type namespace: declaring both
`struct Foo` and `enum Foo` is a hard error.

## Statements

### `match`

```rust
match scrutinee {
    pattern => { body },
    pattern => { body },
}
```

Each arm has a pattern, the `=>` arrow, and a brace-delimited body of
statements. Arms are separated by commas; a trailing comma is allowed.

Pattern forms:

- `_` — wildcard. Matches anything. Binds nothing.
- `name` — variable pattern. Matches anything. Binds the matched value
  to `name` in the arm's body.
- A literal — `0`, `-3`, `true`, `"foo"`. Matches by equality.
- `EnumName::Variant` — variant pattern. Comes in three shapes
  matching the variant's own form:
  - `Color::Red` for unit variants.
  - `Maybe::Some(p)` for tuple variants. Each sub-pattern matches one
    positional value.
  - `Shape::Circle { radius }` for struct variants. The shorthand
    `{ field }` binds `field` by name; the long form
    `{ field: pattern }` matches with a nested sub-pattern. Unmentioned
    fields are simply not bound.

Patterns are checked first-arm-wins at runtime.

**Exhaustiveness.** Matches on enum-typed scrutinees must cover every
variant or include a catchall (`_` or a variable pattern). Matches on
non-enum scrutinees (e.g. an `i64`) require a catchall, since the
checker cannot enumerate all values. Arms placed after a catchall are
rejected at compile time as unreachable.

## Statements (cont.)

| Form                          | Meaning                           |
|-------------------------------|-----------------------------------|
| `let x = expr;`               | Declare, infer type               |
| `let x: T = expr;`            | Declare, check declared type      |
| `let mut x = expr;`           | Declare, allow reassignment       |
| `x = expr;`                   | Assign to existing binding        |
| `x.field = expr;`             | Assign through a field access     |
| `if cond { ... } else { ... }`| `else` is optional                |
| `while cond { ... }`          | Loops while the condition holds   |
| `return expr;` / `return;`    | Return from the current function  |
| `match expr { arms }`         | Pattern match (see above)         |
| `println!(fmt, args...);`     | Print to standard output          |
| `expr;`                       | Expression statement (rare)       |

The `mut` keyword is parsed and **enforced**. Plain `let` declares an
immutable binding; reassigning it (or assigning through a field access
whose root is immutable) is a static error. `let mut` opts in to
reassignment. Function parameters and pattern bindings are always
immutable.

## Expressions

### Function calls

`f(arg1, arg2)`. Arity must match the declaration; each argument's type
must match the declared parameter type.

### Struct literals

```rust
let p = Point { x: 1, y: 2 };
```

Every declared field must be set exactly once. The expression's value
has the named struct type.

### Variant construction

```rust
let r = Color::Red;
let m = Maybe::Some(42);
let c = Shape::Circle { radius: 5 };
```

The form must match the variant's declared shape (unit, tuple, or
struct). Argument types and field types are checked against the variant
declaration. The expression's value has the enum's type, not the
variant's name.

### Field access

`p.x` reads field `x` of struct value `p`. Field accesses chain:
`outer.inner.value`.

### `println!`

```rust
println!("hello");
println!("x = {}", 42);
println!("{} + {} = {}", 1, 2, 3);
```

The format string must be `string`. Each `{}` consumes one argument and
formats it with the runtime's default rendering: integers print as
decimal, `bool` as `true`/`false`, strings as themselves, structs as
`TypeName { field: value, ... }`, and enum variants as
`Enum::Variant`, `Enum::Variant(value, ...)`, or
`Enum::Variant { field: value, ... }` depending on the variant's
shape. Use `{{` and `}}` for literal braces. Extra arguments without
placeholders are appended separated by spaces; this is a convenience,
not a feature to lean on.

## Runtime model

Carpel is a tree-walking interpreter. There is no compilation to
bytecode, no garbage collection (Python's reference counting suffices),
no concurrency. Programs run top-to-bottom starting from `main`.

Runtime errors include division by zero, modulo by zero, and println!
placeholder/argument count mismatches. These print as

    runtime error: division by zero

and exit with code 1.

## What this version does not have

- Generics, traits, lifetimes, references.
- Mutability enforcement at compile time (the `mut` keyword is parsed
  but not enforced).
- Arrays, vectors, slices, iterators.
- Closures, function values, higher-order functions.
- A standard library beyond `println!`.
- Modules or imports.
- Guards on match arms (`x if x > 0 => ...`).
- Or-patterns (`A | B => ...`).

These are intentional omissions, not bugs. Each could be added in a
future revision; none is implied by what currently exists.
