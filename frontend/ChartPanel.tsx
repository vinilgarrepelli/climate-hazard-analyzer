import { useState } from 'react';
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Analysis } from './types';

const metrics = [
  { key: 'heatwave_days', name: 'Heatwave days', unit: 'days / year' },
  { key: 'event_count', name: 'Frequency', unit: 'events / year' },
  { key: 'mean_intensity_c', name: 'Intensity', unit: '°C above threshold' },
  { key: 'mean_duration_days', name: 'Duration', unit: 'days / event' },
] as const;

export default function ChartPanel({ result }: { result: Analysis }) {
  const [metricKey, setMetricKey] = useState<string>('heatwave_days');
  const metric = metrics.find(m => m.key === metricKey)!;
  const trend = result.trends[metric.key];
  const data = result.annual.map(row => ({
    ...row,
    plotted: row.reliable ? row[metric.key] : null,
    regression: trend?.available ? (trend.slope_per_year ?? 0) * row.year + (trend.intercept ?? 0) : null,
  }));
  return <section className="card chart-card" aria-label="Interactive annual heatwave chart">
    <div className="section-heading"><div><p className="eyebrow">THE LONG VIEW</p><h2>A changing heat signature</h2></div><span className="subtle">{result.request.start_year} — {result.request.end_year}</span></div>
    <div className="metric-tabs" role="group" aria-label="Chart metric">{metrics.map(m => <button key={m.key} aria-pressed={metricKey === m.key} className={metricKey === m.key ? 'active' : ''} onClick={() => setMetricKey(m.key)}>{m.name}</button>)}</div>
    <p className="chart-unit">{metric.unit}</p>
    <div className="chart-wrap" role="img" aria-label={`${metric.name} by year. Exact values are available in the annual data tab.`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 12, right: 12, left: -20, bottom: 4 }} accessibilityLayer>
          <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e5e9e1" />
          <XAxis dataKey="year" axisLine={false} tickLine={false} minTickGap={30} tick={{ fill: '#748078', fontSize: 12 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: '#748078', fontSize: 12 }} allowDecimals={metric.key !== 'event_count'} />
          <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e0e7dc', boxShadow: '0 8px 30px #153d3512' }} labelFormatter={label => `Year ${label}`} formatter={(value, name) => [typeof value === 'number' ? value.toFixed(metric.key === 'event_count' ? 0 : 1) : 'No reliable data', name]} />
          <Bar dataKey="plotted" name={metric.name} fill="#d18055" radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          {metric.key === 'heatwave_days' && <Line type="monotone" dataKey="rolling_days" name="3-year rolling average" stroke="#153d35" strokeWidth={2.4} dot={false} connectNulls={false} isAnimationActive={false} />}
          {trend?.available && <Line type="linear" dataKey="regression" name="Linear trend" stroke="#7c9c67" strokeWidth={1.8} strokeDasharray="6 5" dot={false} isAnimationActive={false} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    <div className="chart-legend"><span><i className="legend-bar" />{metric.name}</span>{metric.key === 'heatwave_days' && <span><i className="legend-line" />3-year average</span>}{trend?.available && <span><i className="legend-dash" />Linear trend</span>}</div>
    <p className="footnote">Years below 95% coverage appear as gaps. A fitted trend describes the series; it does not establish causation.</p>
  </section>;
}
