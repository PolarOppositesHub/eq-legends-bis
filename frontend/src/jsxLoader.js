import { transformSync } from 'esbuild'
import { readFileSync } from 'node:fs'

export async function load(url, context, nextLoad) {
  if (!url.endsWith('.jsx')) return nextLoad(url, context)
  const source = readFileSync(new URL(url), 'utf8')
  const transformed = transformSync(source, {
    loader: 'jsx',
    format: 'esm',
    jsx: 'automatic',
    sourcefile: url,
  })
  return {
    format: 'module',
    source: transformed.code,
    shortCircuit: true,
  }
}
