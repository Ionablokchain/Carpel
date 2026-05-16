// A traffic-light state machine. Three states; `next()` advances to the
// following one. Demonstrates a `match` whose arms each return an enum
// value, and an enum used both as input and output.

enum Light {
    Red,
    Yellow,
    Green,
}

fn next(l: Light) -> Light {
    match l {
        Light::Red    => { return Light::Green; },
        Light::Green  => { return Light::Yellow; },
        Light::Yellow => { return Light::Red; },
    }
    return l;
}

fn describe(l: Light) -> string {
    match l {
        Light::Red    => { return "stop"; },
        Light::Yellow => { return "slow down"; },
        Light::Green  => { return "go"; },
    }
    return "?";
}

fn main() {
    let mut l = Light::Red;
    let mut i = 0;
    while i < 6 {
        println!("step {}: {}", i, describe(l));
        l = next(l);
        i = i + 1;
    }
}
