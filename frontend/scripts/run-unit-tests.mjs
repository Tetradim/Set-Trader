import { build } from 'esbuild';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const srcDir = path.join(root, 'src');
const outDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sentinel-unit-'));

async function findTests(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return findTests(fullPath);
    return entry.name.endsWith('.test.ts') ? [fullPath] : [];
  }));
  return files.flat();
}

const tests = await findTests(srcDir);

if (tests.length === 0) {
  console.log('No unit tests found.');
  process.exit(0);
}

const bundledTests = await Promise.all(tests.map(async (testFile) => {
  const outFile = path.join(
    outDir,
    path.relative(srcDir, testFile).replace(/[\\/]/g, '__').replace(/\.ts$/, '.mjs'),
  );

  await build({
    entryPoints: [testFile],
    outfile: outFile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node20',
    sourcemap: 'inline',
    logLevel: 'silent',
  });

  return outFile;
}));

let failures = 0;

for (const testFile of bundledTests) {
  try {
    await import(pathToFileURL(testFile).href);
  } catch (error) {
    failures += 1;
    console.error(error);
  }
}

if (failures > 0) {
  console.error(`${failures} unit test file(s) failed.`);
  process.exit(1);
}

console.log(`${tests.length} unit test file(s) passed.`);
