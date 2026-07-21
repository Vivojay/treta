import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    coverage: {
      include: ['src/lib/**/*.ts'],
      provider: 'v8',
      reporter: ['text'],
      thresholds: {
        branches: 85,
        functions: 85,
        lines: 85,
        statements: 85
      }
    },
    environment: 'node'
  }
});
