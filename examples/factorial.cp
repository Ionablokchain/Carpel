// Classic recursive factorial. Demonstrates user-defined functions,
// recursion, integer arithmetic, and conditional control flow.

fn factorial(n: i64) -> i64 {
    if n <= 1 {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    let n = 10;
    let result = factorial(n);
    println!("{}! = {}", n, result);
}
