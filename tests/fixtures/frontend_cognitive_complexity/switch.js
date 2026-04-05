// switch without cases: +1 for switch
function switchOnly(x) {
    switch (x) {
        default:
            return 'default';
    }
}

// switch with cases: +1 (switch) + 2 (two cases) = +3
function switchWithCases(x) {
    switch (x) {
        case 1:
            return 'one';
        case 2:
            return 'two';
        default:
            return 'other';
    }
}

// nested switch in if: +1 (if) + 1 (switch) + 1 (case) + 1 (case) = +4
function nestedSwitch(x, y) {
    if (x > 0) {
        switch (y) {
            case 1:
                return 'a';
            case 2:
                return 'b';
        }
    }
    return 'default';
}
