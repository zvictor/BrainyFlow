/**
 * @see https://prettier.io/docs/configuration
 * @type {import("prettier").Config}
 */
const config = {
  editorconfig: true,
  semi: false,
  useTabs: false,
  singleQuote: true,
  arrowParens: 'always',
  tabWidth: 2,
  printWidth: 130,
  trailingComma: 'all',
  plugins: ['@ianvs/prettier-plugin-sort-imports'],
  importOrderTypeScriptVersion: '5.4.5',
  importOrder: [
    '<BUILTIN_MODULES>', // Node.js built-in modules
    '^(zod/(.*)$)|^(zod$)',
    '^(react/(.*)$)|^(react$)',
    '^(next/(.*)$)|^(next$)',
    // third-party modules that do not start with @
    '^[\\w-]+$',
    '<THIRD_PARTY_MODULES>',
    '^~/(.*)$',
    '^@/lib/(.*)$',
    '^@/modules/(.*)$',
    '^@/app/(.*)$',
    '^@/config/(.*)$',
    '^@/styles/(.*)$',
    '^@/(.*)$',
    '^[.]',
    '^[./]',
    '',
    '<TYPES>^(node:)',
    '^@types/(.*)$',
    '<TYPES>',
    '^@/types/(.*)$',
    '<TYPES>^[.]',
    '^./types$',
  ],
}

export default config
