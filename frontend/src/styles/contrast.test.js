import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// WCAG 2.1: 4.5:1 for normal text, 3:1 for large text and for the boundaries of controls (colour contrast cannot be
// measured in jsdom, so it is checked here from the design tokens themselves).
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'tokens.css'), 'utf8');
const token = (name) => {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(css);
  if (!match) throw new Error(`token ${name} not found`);
  return match[1];
};

function luminance(hex) {
  const channels = [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255);
  const [r, g, b] = channels.map((value) => (value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

const BACKGROUNDS = ['bg', 'surface', 'surface-2'];

describe('colour contrast of the design tokens', () => {
  it('computes contrast the way WCAG does', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 0);
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 1);
  });

  it.each(['text', 'text-2', 'text-3', 'accent'])('%s text is readable on every surface (4.5:1)', (name) => {
    for (const background of BACKGROUNDS) {
      expect(contrast(token(name), token(background)), `${name} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(['sev-critical', 'sev-high', 'sev-medium', 'sev-low', 'sev-info', 'observed', 'derived', 'danger', 'success', 'warning'])('the %s colour of badges and labels is readable (4.5:1)', (name) => {
    for (const background of BACKGROUNDS) {
      expect(contrast(token(name), token(background)), `${name} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('white text on the button colours is readable', () => {
    expect(contrast('#ffffff', token('accent-button'))).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#ffffff', token('accent-button-hover'))).toBeGreaterThanOrEqual(4.5);
  });

  it('the boundary of an input can be seen (3:1)', () => {
    for (const background of ['bg', 'surface']) {
      expect(contrast(token('control-border'), token(background)), `control border on ${background}`).toBeGreaterThanOrEqual(3);
    }
  });
});
