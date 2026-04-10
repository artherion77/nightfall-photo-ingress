// Editor-only type shim for host VS Code environments where
// `@playwright/test` is not installed locally. Runtime E2E tests execute
// inside the dev-photo-ingress container which provides real Playwright types.
//
// `test` is declared as a callable object so both the call form
// (test('name', fn)) and method forms (test.describe, test.skip, …) are
// accepted. Using (...args: any[]) as the call signature lets TypeScript
// accept any callback, including those with explicit fixture annotations.
//
// Also declares `process` so the SvelteKit tsconfig (which excludes node
// globals from its lib set) does not report an error in playwright.config.ts.
declare const process: { env: Record<string, string | undefined> };

declare module '@playwright/test' {
  export const test: {
    (...args: any[]): any;
    describe(...args: any[]): any;
    skip(...args: any[]): any;
    only(...args: any[]): any;
    use(...args: any[]): any;
    extend(...args: any[]): any;
    beforeAll(...args: any[]): any;
    afterAll(...args: any[]): any;
    beforeEach(...args: any[]): any;
    afterEach(...args: any[]): any;
  };
  export const expect: any;
  export function defineConfig(...args: any[]): any;
  export const devices: Record<string, any>;
  export type Page = any;
  export type Browser = any;
  export type BrowserContext = any;
  export type Locator = any;
  export type Request = any;
  export type Response = any;
  export type Route = any;
  export type TestInfo = any;
}
