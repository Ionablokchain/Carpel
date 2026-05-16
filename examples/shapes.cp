// Enum + match: the canonical "sum type" demo. Three shapes, each with
// its own payload, and a function that pattern-matches to compute the area.

enum Shape {
    Circle { radius: i64 },
    Rectangle { width: i64, height: i64 },
    Nothing,
}

// Note: the type checker enforces that this `match` covers every variant.
// Try removing the `Shape::Nothing` arm and the compiler will refuse the
// program with a non-exhaustive-match error.
fn area(s: Shape) -> i64 {
    match s {
        Shape::Circle { radius } => {
            return 3 * radius * radius;     // pi approximated by 3
        },
        Shape::Rectangle { width, height } => {
            return width * height;
        },
        Shape::Nothing => {
            return 0;
        },
    }
    return 0;
}

fn main() {
    let c = Shape::Circle { radius: 5 };
    let r = Shape::Rectangle { width: 4, height: 6 };
    let n = Shape::Nothing;
    println!("circle area    = {}", area(c));
    println!("rectangle area = {}", area(r));
    println!("nothing area   = {}", area(n));
}
