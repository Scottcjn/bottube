import { defineConfig } from 'tsup';

export default defineConfig({
  entry: ['src/index.ts'],
  format: ['cjs', 'esm'],
  dts: false, // Skip type generation for now - use tsc separately if needed
  outDir: 'dist',
  clean: true,
  tsconfig: 'tsconfig.json',
});
