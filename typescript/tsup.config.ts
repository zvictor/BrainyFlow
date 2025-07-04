import type { Options } from 'tsup'

export const tsup: Options = {
  clean: true,
  dts: true,
  format: ['cjs', 'esm'],
  minify: true,
  bundle: true,
  entryPoints: ['brainyflow.ts'],
  outDir: 'dist',
}
