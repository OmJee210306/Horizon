import { LayoutDashboard, CircleDollarSign, Activity, Database, BookOpenCheck } from 'lucide-react';

export const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/revenue', label: 'Revenue Analytics', icon: CircleDollarSign },
  { to: '/churn', label: 'Churn Intelligence', icon: Activity },
  { to: '/sources', label: 'Data Sources', icon: Database },
  { to: '/methodology', label: 'Methodology', icon: BookOpenCheck }
];
