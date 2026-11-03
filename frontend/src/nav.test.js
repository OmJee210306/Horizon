import { describe, it, expect } from 'vitest';
import { NAV } from './nav';
describe('HORIZON navigation', () => {
  it('contains all five dashboard sections', () => {
    expect(NAV.map((item) => item.label)).toEqual([
      'Overview',
      'Revenue Analytics',
      'Churn Intelligence',
      'Data Sources',
      'Methodology',
    ]);
  });
  it('has unique navigation paths', () => {
    const paths = NAV.map((item) => item.to);
    expect(new Set(paths).size).toBe(paths.length);
  });
  it('uses the overview route as the exact root route', () => {
    expect(NAV[0].to).toBe('/');
    expect(NAV[0].end).toBe(true);
  });
  it('provides an icon for every navigation item', () => {
    NAV.forEach((item) => {
      expect(item.icon).toBeDefined();
    });
  });
});
