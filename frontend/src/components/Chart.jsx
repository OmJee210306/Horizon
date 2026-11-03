import createPlotlyComponent from 'react-plotly.js/factory';
import Plotly from 'plotly.js-basic-dist-min';
import { useApp } from '../context';
import { Skeleton } from './ui';

const Plot = createPlotlyComponent(Plotly);
export const COLORS = { accent: '#6c7bff', teal: '#2dd4bf', violet: '#a78bfa', amber: '#f59e4b', rose: '#ef5b6b', slate: '#8b97ad' };

export default function Chart({ data, layout = {}, height = 300, loading }) {
  const { theme } = useApp();
  if (loading) return <Skeleton h={height} />;
  const dark = theme === 'dark';
  const grid = dark ? 'rgba(148,163,184,.12)' : 'rgba(15,23,42,.08)';
  const text = dark ? '#94a3b8' : '#52607a';
  const { xaxis, yaxis, ...rest } = layout;
  const axis = (a) => ({ gridcolor: grid, zeroline: false, linecolor: grid, tickfont: { color: text }, automargin: true, ...a });
  const final = {
    autosize: true, height, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter, system-ui, sans-serif', color: text, size: 12 },
    margin: { l: 48, r: 14, t: 10, b: 36 },
    legend: { orientation: 'h', y: 1.12, x: 0, font: { color: text } },
    hoverlabel: { bgcolor: dark ? '#0b1224' : '#fff', bordercolor: grid, font: { color: dark ? '#e8edf7' : '#0f172a', family: 'Inter' } },
    xaxis: axis(xaxis), yaxis: axis(yaxis), ...rest
  };
  return <Plot data={data} layout={final} config={{ displayModeBar: false, responsive: true }} useResizeHandler style={{ width: '100%', height }} />;
}
