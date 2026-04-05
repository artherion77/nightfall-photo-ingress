// Direct recursion: +1 (bonus for recursion signal)
function factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

// Recursion with condition: +1 (if) + 1 (recursion) = +2
function fibonacci(n) {
    if (n <= 1) {
        return n;
    }
    return fibonacci(n - 1) + fibonacci(n - 2);
}
