// TypeScript: if with generic: +1
function generic<T>(items: T[]): T | null {
    if (items.length === 0) {
        return null;
    }
    return items[0];
}

// TypeScript with interface check: +1 (as) + 1 (if) + 2 (nested if) = +4
function processTyped(obj: any): string {
    if (obj instanceof Error) {
        if (obj.message) {
            return obj.message;
        }
    }
    return 'unknown';
}
