import js from '@eslint/js';
import globals from 'globals';
import svelte from 'eslint-plugin-svelte';
import ts from 'typescript-eslint';

export default ts.config(
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    files: ['**/*.svelte', '**/*.svelte.ts'],
    languageOptions: {
      parserOptions: {
        parser: ts.parser
      }
    }
  },
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node }
    }
  },
  {
    ignores: ['.svelte-kit/', 'build/', 'coverage/']
  }
);
