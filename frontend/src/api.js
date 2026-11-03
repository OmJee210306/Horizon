import axios from 'axios';
import { API_URL } from './config';

const api = axios.create({ baseURL: API_URL, timeout: 25000 });

api.interceptors.response.use(
  (r) => r,
  (e) => {
    e.friendly = e.response
      ? e.response.data?.detail || `Request failed (${e.response.status})`
      : 'Cannot reach the HORIZON API. Make sure the backend is running on ' + API_URL.replace(/\/api$/, '') + '.';
    return Promise.reject(e);
  }
);

const get = async (url, params) => (await api.get(url, { params })).data;
const clean = (o = {}) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v != null));

export const getOverview = () => get('/overview');
export const getMonthlyRevenue = () => get('/revenue/monthly');
export const getRegions = () => get('/revenue/regions');
export const getPlans = () => get('/revenue/plans');
export const getInvoiceStatus = () => get('/revenue/invoice-status');
export const getAccounts = (p) => get('/revenue/accounts', clean(p));
export const getChurnSummary = () => get('/churn/summary');
export const getChurnFeatures = () => get('/churn/features');
export const getChurnSegments = () => get('/churn/segments');
export const getChurnBands = () => get('/churn/numeric-bands');
export const getCustomers = (p) => get('/churn/customers', clean(p));
export const getChurnModelInfo = () => get('/churn/model-info');
export const predictChurn = async (payload) => (await api.post('/churn/predict', payload)).data;
export const getSources = () => get('/metadata/sources');
export const getHealth = async () => {
  const t = performance.now();
  const d = await get('/health');
  return { ...d, latency: Math.round(performance.now() - t) };
};
export const errorMessage = (e) => e?.friendly || e?.message || 'Something went wrong.';
