import { describe, it, expect } from 'vitest';
import {
  toDate,
  monthLabel,
  longDate,
  pretty,
  sum,
  ratio,
  delta,
  parseContributors,
  prettyBand,
  bandStart,
} from './format';
describe('HORIZON formatting utilities', () => {
  it('converts an ISO date correctly', () => {
    const date = toDate('2025-01-15');
    expect(date.getFullYear()).toBe(2025);
    expect(date.getMonth()).toBe(0);
    expect(date.getDate()).toBe(15);
  });
  it('formats a month label', () => {
    expect(monthLabel('2025-01-15')).toBe('Jan 25');
  });
  it('formats a long date', () => {
    expect(longDate('2025-01-15')).toBe('Jan 15, 2025');
  });
  it('returns a fallback for an empty date', () => {
    expect(longDate('')).toBe('\u2014');
  });
  it('converts underscores into readable labels', () => {
    expect(pretty('enterprise_plan')).toBe('Enterprise plan');
  });
  it('handles null labels safely', () => {
    expect(pretty(null)).toBe('');
  });
  it('calculates sums correctly', () => {
    expect(sum([{ amount: 10 }, { amount: 20 }, { amount: 5 }], 'amount')).toBe(35);
  });
  it('calculates ratios as percentages', () => {
    expect(ratio(25, 100)).toBe(25);
  });
  it('handles division by zero in ratios', () => {
    expect(ratio(25, 0)).toBe(0);
  });
  it('calculates percentage change', () => {
    expect(delta(150, 100)).toBe(50);
  });
  it('returns null when previous value is zero', () => {
    expect(delta(150, 0)).toBeNull();
  });
  it('parses model contributors', () => {
    expect(parseContributors('feature_a (0.75); feature_b (-0.25)')).toEqual([
      { name: 'Feature a', value: 0.75 },
      { name: 'Feature b', value: -0.25 },
    ]);
  });
  it('formats numeric bands', () => {
    expect(prettyBand('[1.234, 5.678)')).toBe('1.23 \u2013 5.68');
  });
  it('extracts the start of a numeric band', () => {
    expect(bandStart('[10, 20)')).toBe(10);
  });
});
