# Carpel Language Reference (v0.1)

This document describes Carpel as it is implemented. Where the
implementation and any earlier specification disagree, the implementation
is authoritative.

## Lexical structure

### Comments

`// line comment` runs to end of line.

### Keywords

```
fn  struct  let  mut  if  else  while  return  true  false
i64  bool  string  unit
```

`println!` is its own keyword-like token (note the trailing `!`).

### Identifiers

`[A-Za-z_][A-Za-z0-9_]*`. Case-sensitive.

### Literals

| Form       | Type    | Notes                              |
|------------|---------|------------------------------------|
| `42`       | i64     | Signed 64-bit integer              |
| `"text"`   | string  | Escapes: `\n \t \r \" \\`           |
| `true`/`false` | bool |                                    |

Negative integers are unary minus applied to a positive literal.

### Operators (precedence, low to high)

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

All binary operators are left-associative.

## Types

| Type     | Notes                                          |
|----------|------------------------------------------------|
| `i64`    | Signed 64-bit integer                          |
| `bool`   | `true` or `false`                              |
| `string` | UTF-8 text                                     |
| `unit`   | The single value `()` (only the return type of void functions) |
| `<Name>` | A user-declared struct                         |

There is no `null`, no `Option`, no nullable types. There is no implicit
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

## Statements

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
| `println!(fmt, args...);`     | Print to standard output          |
| `expr;`                       | Expression statement (rare)       |

The `mut` keyword is parsed but not enforced in v0.1: assignment to a
non-mut variable is allowed. The type checker will gain this in v0.2.

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
decimal, `bool` as `true`/`false`, strings as themselves, and structs
as `TypeName { field: value, ... }`. Use `{{` and `}}` for literal
braces. Extra arguments without placeholders are appended separated by
spaces; this is a convenience, not a feature to lean on.

## Runtime model

Carpel is a tree-walking interpreter. There is no compilation to
bytecode, no garbage collection (Python's reference counting suffices),
no concurrency. Programs run top-to-bottom starting from `main`.

Runtime errors include division by zero, modulo by zero, and println!
placeholder/argument count mismatches. These print as

    runtime error: division by zero

and exit with code 1.

## What v0.1 does not have

- Generics, traits, lifetimes, references.
- Mutability enforcement at compile time.
- Pattern matching, `match`, sum types, enums.
- Arrays, vectors, slices, iterators.
- Closures, function values, higher-order functions.
- A standard library beyond `println!`.
- Modules or imports.

These are intentional omissions for v0.1, not bugs. Each could be added
in a future revision; none is implied by what currently exists.
