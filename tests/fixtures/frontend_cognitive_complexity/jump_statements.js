// break statement: +1
function loopWithBreak(arr) {
    for (let i = 0; i < arr.length; i++) {
        if (arr[i] === 'target') {
            break;
        }
    }
}

// continue statement: +1
function loopWithContinue(arr) {
    for (let i = 0; i < arr.length; i++) {
        if (arr[i] === 'skip') {
            continue;
        }
        process(arr[i]);
    }
}

// throw statement: +1
function throwError(x) {
    if (x < 0) {
        throw new Error('negative');
    }
    return x;
}

// Total: +1 (if) + 1 (throw) = +2
function multiJumps(a, b) {
    if (a < 0) {
        throw new Error('a is negative');
    }
    if (b > 100) {
        return null;
    }
    return a + b;
}
