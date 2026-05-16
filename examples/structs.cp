// Carpel structs: typed records with named fields. The type checker
// verifies that all fields are set, none are duplicated, and each value
// has the declared type.

struct Point {
    x: i64,
    y: i64,
}

struct Rectangle {
    top_left: Point,
    bottom_right: Point,
}

fn distance_squared(a: Point, b: Point) -> i64 {
    let dx = a.x - b.x;
    let dy = a.y - b.y;
    return dx * dx + dy * dy;
}

fn width(r: Rectangle) -> i64 {
    return r.bottom_right.x - r.top_left.x;
}

fn height(r: Rectangle) -> i64 {
    return r.bottom_right.y - r.top_left.y;
}

fn area(r: Rectangle) -> i64 {
    return width(r) * height(r);
}

fn main() {
    let origin = Point { x: 0, y: 0 };
    let far = Point { x: 3, y: 4 };
    println!("distance_squared = {}", distance_squared(origin, far));

    let r = Rectangle {
        top_left: Point { x: 0, y: 0 },
        bottom_right: Point { x: 10, y: 5 },
    };
    println!("area = {}", area(r));
}
