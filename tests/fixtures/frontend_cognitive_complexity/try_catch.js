// try-catch: +1 for catch
function tryCatch(x) {
    try {
        return riskyOperation(x);
    } catch (e) {
        return null;
    }
}

// nested catch in loop: +1 (loop) + (1+1) (catch nested in loop) = +3
function loopWithTryCatch(items) {
    for (const item of items) {
        try {
            process(item);
        } catch (e) {
            console.error(e);
        }
    }
}
