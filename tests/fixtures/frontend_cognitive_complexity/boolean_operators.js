// if with no operators: +1
function simpleCondition(x) {
    if (x > 0) {
        return 'positive';
    }
    return 'zero or negative';
}

// if with one && operator: +1 + 1 = +2
function andCondition(x, y) {
    if (x > 0 && y > 0) {
        return 'both positive';
    }
    return 'not both positive';
}

// if with two && operators: +1 + 2 = +3
function multiAnd(a, b, c) {
    if (a > 0 && b > 0 && c > 0) {
        return 'all positive';
    }
    return 'not all positive';
}

// if with && and ||: +1 + 3 = +4 (&&, ||, &&)
function mixedOperators(a, b, c, d) {
    if (a > 0 && b > 0 || c > 0 && d > 0) {
        return 'at least one pair positive';
    }
    return 'no pair positive';
}
