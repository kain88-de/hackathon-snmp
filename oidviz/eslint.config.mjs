import pluginVue from 'eslint-plugin-vue';
import tsParser from '@typescript-eslint/parser';
import vueParser from 'vue-eslint-parser';

export default [
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        sourceType: 'module',
      },
    },
    rules: {
      // Disable all @typescript-eslint rules — covered by Oxlint + Biome
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
  {
    // Only lint .vue files — .ts files are fully covered by Oxlint + Biome + vue-tsc
    ignores: ['src/**/*.ts', 'src/lib/types.gen.ts'],
  },
];
