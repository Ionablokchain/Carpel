// Mutability is enforced statically: a binding declared with `let` cannot
// be reassigned, nor can its fields be modified. Use `let mut` to opt in.

struct Counter {
    value: i64,
    step: i64,
}

fn main() {
    // Immutable: the counter's setup is fixed.
    let initial = Counter { value: 0, step: 1 };

    // Mutable: we will reassign and update fields below.
    let mut c = Counter { value: initial.value, step: initial.step };

    let mut i = 0;
    while i < 5 {
        c.value = c.value + c.step;
        println!("tick {}: value = {}", i, c.value);
        i = i + 1;
    }

    // Reassign the whole binding to a fresh counter.
    c = Counter { value: 100, step: 10 };
    println!("reset: value = {}, step = {}", c.value, c.step);

    // The following would all be rejected at compile time:
    //   initial.value = 5;        -- 'initial' is not mut
    //   initial = c;              -- 'initial' is not mut
    // Try removing `mut` from `c` and see what happens.
}
