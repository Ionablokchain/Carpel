// FizzBuzz, the canonical interview problem. Demonstrates a `while`
// loop, mutable assignment, and chained `if/else if/else`.

fn main() {
    let mut i = 1;
    while i <= 15 {
        if i % 15 == 0 {
            println!("FizzBuzz");
        } else if i % 3 == 0 {
            println!("Fizz");
        } else if i % 5 == 0 {
            println!("Buzz");
        } else {
            println!("{}", i);
        }
        i = i + 1;
    }
}
