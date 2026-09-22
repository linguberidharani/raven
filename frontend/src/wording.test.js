import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// Spec section 14: no encryption or decryption wording in the interface (the report of the API may name encryption only
// in its limitations, which the interface shows as the API sends it). Nor kill-chain stages, which real data does not have.
const here = dirname(fileURLToPath(import.meta.url));

function sources() {
  return readdirSync(here, { recursive: true })
    .map(String)
    .filter((file) => /\.(js|jsx|css)$/.test(file) && !/\.test\.(js|jsx)$/.test(file) && !file.startsWith('test'))
    .map((file) => ({ file, text: readFileSync(join(here, file), 'utf8') }));
}

describe('wording of the interface', () => {
  it('has source files to look at', () => {
    expect(sources().length).toBeGreaterThan(40);
  });

  it('never talks about encryption or decryption', () => {
    const found = sources().filter(({ text }) => /encrypt|decrypt/i.test(text)).map(({ file }) => file);
    expect(found).toEqual([]);
  });

  it('has no kill-chain stages, which real data does not have', () => {
    const found = sources().filter(({ text }) => /kill[- ]?chain/i.test(text)).map(({ file }) => file);
    expect(found).toEqual([]);
  });
});
