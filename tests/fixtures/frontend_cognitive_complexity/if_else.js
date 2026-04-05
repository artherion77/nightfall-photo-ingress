// Single if: +1
function singleIf(x) {
    if (x > 0) {
        return x;
    }
    return 0;
}

// if + else if: +1 +1 = +2
function ifElseIf(x) {
    if (x > 10) {
        return 'large';
    } else if (x > 0) {
        return 'small';
    }
    return 'zero';
}
