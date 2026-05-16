// Carpel's poor-man's Option: a tuple variant carrying a value, plus
// a unit variant for the empty case. Used here to express division that
// might fail.

enum MaybeInt {
    Some(i64),
    None,
}

fn safe_div(a: i64, b: i64) -> MaybeInt {
    if b == 0 {
        return MaybeInt::None;
    }
    return MaybeInt::Some(a / b);
}

fn report(label: string, m: MaybeInt) {
    match m {
        MaybeInt::Some(v) => {
            println!("{} = {}", label, v);
        },
        MaybeInt::None => {
            println!("{} = undefined", label);
        },
    }
}

fn main() {
    report("10 / 2", safe_div(10, 2));
    report("10 / 0", safe_div(10, 0));
    report("7 / 3",  safe_div(7, 3));
}
