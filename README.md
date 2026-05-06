# Carpel

**A safe systems language without ceremony.**

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Version](https://img.shields.io/badge/version-0.1.0--alpha-orange)]()
[![Discord](https://img.shields.io/badge/chat-on%20discord-7289da)]()

Carpel is a compiled, statically typed programming language designed for systems development. It guarantees memory safety without a garbage collector, eliminates boilerplate like explicit lifetimes and manual concurrency markers, and introduces **arenas** as a first‑class abstraction for high‑performance, bulk memory management.

If you love the power and safety of Rust but wish the syntax didn't get in the way, Carpel might be for you.

---

## Why Carpel?

Modern systems languages demand both control and safety, but that often comes with a steep learning curve. Carpel rethinks the trade‑off:

- **No `'a`.** Lifetimes are fully inferred. Write signatures that read like pseudocode.
- **No `Send`, `Sync`, `Pin`.** The compiler deduces sendability and handles async pinning automatically.
- **Arenas, not `Box`es.** Temporary data lives in explicitly scoped memory regions that are freed in bulk—zero allocation overhead, no garbage collector.
- **Fearless concurrency.** Channels and shared state work out of the box, with automatic thread‑safety verification.

The result is a language that keeps you in the driver's seat while getting out of your way.

---

## Features

- **Ownership with inferred lifetimes** – Move semantics and borrowing without lifetime annotations.
- **Arenas** – Bulk allocation and deallocation for hierarchical or temporary data.
- **Traits and generics** – Zero‑cost abstractions with clean, short constraint lists.
- **Built‑in async** – `async`/`await` with no `Pin` or `Box::pin` required.
- **Interoperable with C** – Call existing C libraries, or expose Carpel functions to other languages.
- **Unsafe escape hatch** – Low‑level operations are explicit and isolated.
- **Fast, single‑binary compiler** – Powered by LLVM for optimised native code.

---

## A Quick Look

```carpel
// Parse and evaluate an arithmetic expression using an arena
enum Expr {
    Number(i32),
    Plus(ref Expr, ref Expr),
    Times(ref Expr, ref Expr),
}

fn eval(e: ref Expr) -> i32 {
    match *e {
        Expr::Number(n) => n,
        Expr::Plus(l, r) => eval(l) + eval(r),
        Expr::Times(l, r) => eval(l) * eval(r),
    }
}

fn main() {
    let buffer: [u8; 4096] = [0; 4096];
    arena tmp: Arena(buffer) {
        let expr = parse_input(&tmp, "3+4*2").unwrap();
        println!("Result: {}", eval(expr)); // 11
    }
}
