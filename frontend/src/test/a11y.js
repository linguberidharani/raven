import axe from 'axe-core';
import { expect } from 'vitest';

// jsdom has no layout or colours, so those rules cannot run here (colour contrast is checked from the tokens instead).
const OPTIONS = {
  runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
  rules: {
    'color-contrast': { enabled: false },
    'scrollable-region-focusable': { enabled: false },
  },
};

/** Fails with a readable list when axe finds an accessibility problem in the part of the page it is given. */
export async function expectNoViolations(root = document.body) {
  // The address probe of the test harness is not part of the interface.
  const results = await axe.run({ include: [root], exclude: [['[data-testid="location"]']] }, OPTIONS);
  const lines = results.violations.map((violation) => `${violation.id} (${violation.impact}): ${violation.help} -> ${violation.nodes.map((node) => node.target.join(' ')).slice(0, 4).join(' | ')}`);
  expect(lines).toEqual([]);
}
