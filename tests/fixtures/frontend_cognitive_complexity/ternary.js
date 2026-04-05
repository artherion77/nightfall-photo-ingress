// ternary (conditional expression): +1
function useTernary(x) {
    return x > 0 ? 'positive' : 'non-positive';
}

// nested ternary: +1 + (1+1) = +3
function nestedTernary(x, y) {
    return x > 0 ? (y > 0 ? 'both' : 'x only') : 'neither';
}
