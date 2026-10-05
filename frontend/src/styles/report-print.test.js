import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// jsdom does not apply external stylesheets, so the on-screen collapse of Report.jsx's extra findings
// (styles/report.css: .report-more) is checked here directly, at the CSS level, instead of by rendering it.
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'report.css'), 'utf8');

describe('the collapsed findings of a report section', () => {
  it('are hidden on screen by default', () => {
    expect(css).toMatch(/\.report-more\s*\{[^}]*display:\s*none/);
  });

  it('appear when the toggle opens the section', () => {
    expect(css).toMatch(/\.report-more\.open\s*\{[^}]*display:\s*block/);
  });

  it('are always shown in a printed or saved-as-PDF report, regardless of the on-screen toggle', () => {
    expect(css).toMatch(/@media print\s*\{[^}]*\.report-more\s*\{[^}]*display:\s*block\s*!important/s);
  });
});
