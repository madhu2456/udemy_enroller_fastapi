declare module '*.css' {}

declare module 'vitest/config' {
  export function defineConfig(config: Record<string, any>): Record<string, any>;
}
