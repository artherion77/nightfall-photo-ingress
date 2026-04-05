// Function 1: simple, score 0
const simple = () => 42;

// Function 2: with if, score 1
function withIf(x) {
    if (x > 0) return x;
    return 0;
}

// Function 3: with nested if and loop, score 1 + (1+1) + 1 = 4
function complex(data) {
    for (const item of data) {
        if (item.active) {
            if (item.priority > 5) {
                process(item);
            }
        }
    }
}
