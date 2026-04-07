// Editor-only type shim for host VS Code/Pylance environments where
// `vitest` is not installed locally. Runtime tests execute in the
// project/container environment that provides real `vitest` types.
declare module 'vitest' {
  export const describe: (...args: any[]) => any;
  export const it: (...args: any[]) => any;
  export const test: (...args: any[]) => any;
  export const expect: (...args: any[]) => any;
  export const vi: any;
  export const beforeAll: (...args: any[]) => any;
  export const beforeEach: (...args: any[]) => any;
  export const afterAll: (...args: any[]) => any;
  export const afterEach: (...args: any[]) => any;
}
