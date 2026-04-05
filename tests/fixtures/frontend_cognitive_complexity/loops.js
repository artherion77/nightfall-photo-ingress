// for loop: +1
function forLoop(arr) {
    for (let i = 0; i < arr.length; i++) {
        console.log(arr[i]);
    }
}

// while loop: +1
function whileLoop(n) {
    while (n > 0) {
        n--;
    }
}

// for..of: +1
function forEach(items) {
    for (const item of items) {
        process(item);
    }
}

// nested loop: 1 + (1+1) = +3
function nestedLoop(matrix) {
    for (let i = 0; i < matrix.length; i++) {
        for (let j = 0; j < matrix[i].length; j++) {
            console.log(matrix[i][j]);
        }
    }
}
