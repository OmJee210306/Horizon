# HORIZON Frontend

React 18 + Vite + Plotly dashboard for the HORIZON analytics API.

## Run (PowerShell)
```powershell
# 1. backend (from D:\Horizon, venv active)
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# 2. frontend (new terminal)
cd D:\Horizon\frontend
npm install
npm run dev
```
Open http://127.0.0.1:5173. The port is fixed because the API's CORS list only allows `:5173`.

## Production build
```powershell
npm run build
npm run preview
```

## Pages
| Route | What it shows |
|---|---|
| Overview | Billing + churn KPIs with sparklines, trend, tier distribution, auto-generated insights |
| Revenue Analytics | Period filter, collection rate, regions, plans, invoice status, top accounts (paged) |
| Churn Intelligence | Risk overview (importance, capture curve), segment/numeric-band explorer, customer explorer with detail drawer and CSV export |
| Data Sources | Source cards, data flow, live API/DB status, governance |
| Methodology | Model facts, tier definitions, limitations |

## Features
Light/dark theme · collapsible sidebar · mobile drawer · `Ctrl/Cmd + K` command palette · currency symbol selector (display only, no conversion) · debounced search and server-side pagination · skeleton loaders, retry and error states · API health polling every 30 s · CSV exports.

## Configuration
Copy `.env.example` to `.env` to point at a different API: `VITE_API_URL=http://127.0.0.1:8000/api`.
Model facts on the Methodology page live in `src/config.js`.

## Structure
```
src/
  api.js  config.js  format.js  hooks.js  context.jsx  nav.js  styles.css
  components/  ui.jsx  Chart.jsx  CustomerDrawer.jsx  CommandPalette.jsx
  pages/       Overview  Revenue  Churn  Sources  Methodology
```
Charts use `plotly.js-basic-dist-min` (bar, line, pie) to keep the bundle small.
