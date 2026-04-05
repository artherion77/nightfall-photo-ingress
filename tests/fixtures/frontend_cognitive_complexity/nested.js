// Nested conditionals with nesting penalty
// Outer if: +1 (nesting 0)
// Inner if: +1 + 1 (nesting 1) = +2
// Total: 3
function nested(x, y) {
    if (x > 0) {
        if (y > 0) {
            return x + y;
        }
    }
    return 0;
}

// Deeply nested: 1 + (1+1) + (1+2) = 1 + 2 + 3 = 6
function deeplyNested(a, b, c) {
    if (a > 0) {
        if (b > 0) {
            if (c > 0) {
                return a + b + c;
            }
        }
    }
    return 0;
}
