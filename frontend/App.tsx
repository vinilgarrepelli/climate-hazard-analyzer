import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, Check, ChevronDown, Download, Globe2, Info, Leaf, LoaderCircle, MapPin, Search, ShieldCheck, Sun, Thermometer, TrendingUp, X } from 'lucide-react';
import type { Analysis, Parameters, Region } from './types';

const ChartPanel = lazy(() => import('./ChartPanel'));
const lastYear = new Date().getFullYear() - 1;
const previewMode = import.meta.env.VITE_PREVIEW_MODE === 'true';
const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const home: Region = { name: 'Hyderabad, India', latitude: 17.385, longitude: 78.4867 };
const initial: Parameters = { latitude: home.latitude, longitude: home.longitude, region_name: home.name, start_year: 1990, end_year: lastYear, hazard: 'heatwave', percentile: 95, min_duration: 3 };
const number = (v: number | null | undefined, decimals = 0) => v == null ? '—' : v.toLocaleString('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
const dateLabel = (date: string) => new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `The request failed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join(' ') : message;
    } catch { /* Preserve a readable message for upstream HTML errors. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function StatCard({ label, value, unit, detail, icon }: { label: string; value: string; unit?: string; detail: string; icon: React.ReactNode }) {
  return <article className="card stat-card"><div className="stat-top"><span>{label}</span><span className="stat-icon">{icon}</span></div><div className="stat-value">{value}<span>{unit}</span></div><p>{detail}</p></article>;
}

function AnnualTable({ result }: { result: Analysis }) {
  return <section className="card data-card"><div className="section-heading"><div><p className="eyebrow">EVERY YEAR, ACCOUNTED FOR</p><h2>Annual observations</h2></div><span className="subtle">Celsius · calendar years</span></div>
    <div className="table-scroll"><table><caption className="sr-only">Annual heatwave indicators and daily data coverage</caption><thead><tr><th scope="col">Year</th><th scope="col">Events</th><th scope="col">Heatwave days</th><th scope="col">Mean duration</th><th scope="col">Intensity above threshold</th><th scope="col">Coverage</th></tr></thead><tbody>{result.annual.map(row => <tr key={row.year} className={!row.reliable ? 'low-coverage' : ''}><th scope="row">{row.year}</th><td>{row.event_count}</td><td>{row.heatwave_days}</td><td>{number(row.mean_duration_days, 1)} days</td><td>{number(row.mean_intensity_c, 2)} °C</td><td><span className={`quality-pill ${!row.reliable ? 'warning' : ''}`}>{number(row.coverage_pct, 1)}% {!row.reliable && '· limited'}</span></td></tr>)}</tbody></table></div>
    <p className="footnote">A zero means no detected events. A dash means intensity is undefined because no heatwave occurred. Low-coverage counts may underestimate the true count.</p>
  </section>;
}

function Methodology({ result }: { result: Analysis }) {
  return <section className="card method-card"><p className="eyebrow">A TRANSPARENT YARDSTICK</p><h2>How the analysis works</h2><p className="method-intro">{result.methodology.definition}</p><div className="method-grid">
    <article><span className="step-number">01</span><h3>One consistent data source</h3><p>Daily maximum temperatures from Open-Meteo’s ERA5 historical reanalysis. The same model is used across decades to keep the comparison consistent.</p><p className="subtle">Grid point: {result.source.grid_latitude}°, {result.source.grid_longitude}° · {result.source.timezone}</p></article>
    <article><span className="step-number">02</span><h3>A fixed reference period</h3><p>The {result.methodology.percentile}th percentile is calculated from every valid daily maximum in 1991–2020. The unrounded threshold is used in detection.</p><p className="subtle">Baseline coverage: {number(result.methodology.baseline_coverage_pct, 2)}%</p></article>
    <article><span className="step-number">03</span><h3>Consecutive means consecutive</h3><p>Missing dates, invalid temperatures, or a day at or below the threshold break a run. Values are checked for units, duplicates, and implausible temperatures.</p><p className="subtle">{result.quality.missing_data_policy}</p></article>
    <article><span className="step-number">04</span><h3>Careful comparisons</h3><p>Annual counts, a 3-year trailing average, and ordinary least squares describe the trend. Equal, non-overlapping periods are compared; a zero starting value never produces a percentage.</p><p className="subtle">Years below 95% coverage are excluded from trend fitting.</p></article>
  </div><div className="method-note"><Info size={18} /><div><strong>Read the limits alongside the results.</strong><p>{result.methodology.threshold_scope} ERA5 represents a grid cell rather than a street or weather station. This indicator does not quantify health impacts or attribute changes to a particular cause.</p><p>{result.methodology.year_attribution}</p></div></div>
  <a href={result.source.documentation_url} target="_blank" rel="noreferrer" className="text-link">Read the data source documentation <ArrowUpRight size={15} /></a></section>;
}

export default function App() {
  const [parameters, setParameters] = useState<Parameters>(initial);
  const [regions, setRegions] = useState<Region[]>([home]);
  const [regionMode, setRegionMode] = useState<'city' | 'coordinates'>('city');
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<Region[]>([]);
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [searchError, setSearchError] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'annual' | 'method'>('overview');
  const [advanced, setAdvanced] = useState(false);
  const [eventsPage, setEventsPage] = useState(0);
  const [mobileFilters, setMobileFilters] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const resultSection = useRef<HTMLElement | null>(null);

  async function runAnalysis(input: Parameters, signal?: AbortSignal) {
    setBusy(true); setError('');
    try {
      const response = await fetch(`${apiBase}/api/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal });
      const data = await parseResponse<Analysis>(response);
      setResult(data); setEventsPage(0); setMobileFilters(false);
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') setError(err.message);
    } finally { if (!signal?.aborted) setBusy(false); }
  }

  useEffect(() => {
    const abort = new AbortController(); controller.current = abort;
    fetch(`${apiBase}/api/regions`, { signal: abort.signal }).then(parseResponse<{ regions: Region[] }>).then(data => setRegions(data.regions)).catch(() => {});
    void runAnalysis(initial, abort.signal);
    return () => abort.abort();
  }, []);

  function chooseRegion(region: Region) {
    setParameters(p => ({ ...p, latitude: region.latitude, longitude: region.longitude, region_name: region.name }));
    setSearchResults([]); setSearch(''); setSearchError('');
    setRegions(prev => prev.some(r => r.name === region.name) ? prev : [...prev, region]);
  }

  async function searchCities() {
    setSearching(true); setSearchError('');
    try {
      const response = await fetch(`${apiBase}/api/geocode?q=${encodeURIComponent(search.trim())}`);
      const data = await parseResponse<{ results: Region[] }>(response);
      setSearchResults(data.results);
      if (!data.results.length) setSearchError('No matching cities. Try another name or enter coordinates.');
    } catch (err) { setSearchError(err instanceof Error ? err.message : 'Could not search cities.'); }
    finally { setSearching(false); }
  }

  async function exportCSV() {
    if (!result) return;
    setExporting(true); setError('');
    try {
      const response = await fetch(`${apiBase}/api/export/csv`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result.request) });
      if (!response.ok) await parseResponse(response);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `heatwave-${result.request.start_year}-${result.request.end_year}.csv`; anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not export the analysis.'); }
    finally { setExporting(false); }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault(); controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    void runAnalysis(parameters, abort.signal);
  }

  const selectionChanged = result && JSON.stringify(parameters) !== JSON.stringify(result.request);
  const comparison = result?.comparison;
  const percentChange = comparison?.percent_change;
  const dayTrend = result?.trends.heatwave_days;
  const displayedEvents = result?.events.slice(eventsPage * 6, (eventsPage + 1) * 6) ?? [];

  return <div className="app-shell">
    <a href="#analysis" className="skip-link">Skip to results</a>
    <aside className={`sidebar ${mobileFilters ? 'mobile-open' : ''}`} aria-label="Analysis controls">
      <div className="brand"><div className="brand-mark"><Sun size={23} /></div><div>Climate Lens<span>HISTORICAL HAZARD INTELLIGENCE</span></div><button className="mobile-close icon-button" aria-label="Close filters" onClick={() => setMobileFilters(false)}><X size={20} /></button></div>
      <div className="sidebar-heading"><span className="sidebar-rule" /> YOUR ANALYSIS</div>
      <form onSubmit={submit} className="controls-form">
        <fieldset disabled={busy}>
        <div className="field-block"><label htmlFor="hazard"><Sun size={15} /> Climate hazard</label><select id="hazard" value="heatwave" disabled><option value="heatwave">Heatwave</option></select><span className="field-help">Consecutive extreme-heat days</span></div>
        <div className="field-block"><label><MapPin size={15} /> Geographic region</label><div className="small-tabs" role="group" aria-label="Region input method"><button type="button" aria-pressed={regionMode === 'city'} className={regionMode === 'city' ? 'active' : ''} onClick={() => setRegionMode('city')}>City</button><button type="button" aria-pressed={regionMode === 'coordinates'} className={regionMode === 'coordinates' ? 'active' : ''} onClick={() => setRegionMode('coordinates')}>Coordinates</button></div>
          {regionMode === 'city' ? <><label htmlFor="city" className="sr-only">Select city</label><select id="city" value={parameters.region_name} onChange={event => { const region = regions.find(r => r.name === event.target.value); if (region) chooseRegion(region); }}>{regions.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}</select><div className="search-box"><Search size={15} /><input aria-label="Search another city" placeholder="Search any city…" minLength={2} maxLength={80} value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); if (search.trim().length >= 2) void searchCities(); } }} /><button type="button" disabled={searching || search.trim().length < 2} aria-label="Find city" onClick={() => { void searchCities(); }}>{searching ? <LoaderCircle size={15} className="spin" /> : <ArrowRight size={15} />}</button></div>{searchError && <p className="field-error" role="status">{searchError}</p>}{searchResults.length > 0 && <ul className="search-results">{searchResults.map(r => <li key={`${r.latitude}-${r.longitude}`}><button type="button" onClick={() => chooseRegion(r)}>{r.name}</button></li>)}</ul>}</> : <><label htmlFor="region-label" className="sr-only">Location name</label><input id="region-label" placeholder="Location name" value={parameters.region_name} maxLength={80} onChange={event => setParameters(p => ({ ...p, region_name: event.target.value }))} required /><div className="coordinate-fields"><div><label htmlFor="latitude">Latitude</label><input id="latitude" type="number" min="-89.9" max="89.9" step="0.0001" value={parameters.latitude} onChange={event => setParameters(p => ({ ...p, latitude: Number(event.target.value) }))} required /></div><div><label htmlFor="longitude">Longitude</label><input id="longitude" type="number" min="-180" max="180" step="0.0001" value={parameters.longitude} onChange={event => setParameters(p => ({ ...p, longitude: Number(event.target.value) }))} required /></div></div></>}
        </div>
        <div className="field-block"><label><BarChart3 size={15} /> Historical period</label><div className="year-fields"><div><label htmlFor="start-year">From</label><input id="start-year" type="number" min="1940" max={parameters.end_year} value={parameters.start_year} onChange={event => setParameters(p => ({ ...p, start_year: Number(event.target.value) }))} required /></div><span>—</span><div><label htmlFor="end-year">To</label><input id="end-year" type="number" min={parameters.start_year} max={lastYear} value={parameters.end_year} onChange={event => setParameters(p => ({ ...p, end_year: Number(event.target.value) }))} required /></div></div><div className="period-presets">{[1990, 2000, 2010].map(year => <button type="button" key={year} onClick={() => setParameters(p => ({ ...p, start_year: year, end_year: lastYear }))}>{year}–{String(lastYear).slice(2)}</button>)}</div><span className="field-help">Complete years, 1940–{lastYear}</span></div>
        <button type="button" className="advanced-toggle" aria-expanded={advanced} onClick={() => setAdvanced(a => !a)}>Heatwave definition <ChevronDown size={15} className={advanced ? 'rotate' : ''} /></button>
        {advanced && <div className="advanced-fields"><div><label htmlFor="percentile">Threshold percentile <strong>{parameters.percentile}th</strong></label><input id="percentile" type="range" min="90" max="99" step="1" value={parameters.percentile} onChange={event => setParameters(p => ({ ...p, percentile: Number(event.target.value) }))} /></div><div><label htmlFor="duration">Minimum consecutive days</label><select id="duration" value={parameters.min_duration} onChange={event => setParameters(p => ({ ...p, min_duration: Number(event.target.value) }))}>{[3, 4, 5, 7, 10].map(days => <option key={days} value={days}>{days} days</option>)}</select></div><p className="field-help">Reference baseline stays fixed at 1991–2020.</p></div>}
        <button className="run-button" type="submit" disabled={busy}>{busy ? <><LoaderCircle size={18} className="spin" /> Analyzing history…</> : <>Run analysis <ArrowRight size={18} /></>}</button>
        {busy && <p className="loading-help" aria-live="polite">A new location may take up to a minute. Repeat queries use the database cache.</p>}
        </fieldset>
      </form>
      <div className="sidebar-note"><ShieldCheck size={19} /><div><strong>Built on real weather history</strong><p>ERA5 reanalysis · Celsius<br />A fixed baseline. Clear assumptions.</p></div></div>
      <div className="sidebar-footer"><Leaf size={14} /> Explore evidence. Understand change.</div>
    </aside>

    <main className="main-content" id="analysis" ref={resultSection}>
      <header className="topbar"><div className="breadcrumb"><Globe2 size={15} /><span>CLIMATE INTELLIGENCE</span><span className="breadcrumb-slash">/</span><span>Heatwaves</span></div><span className="data-badge"><i /> HISTORICAL ERA5 DATA</span></header>
      <section className="page-heading"><div><p className="eyebrow">PATTERNS, BEYOND THE WEATHER</p><h1>Understand the history of heat.</h1><p>Explore how extreme heat has changed, one region at a time.</p></div><div className="heading-actions"><button className="secondary-button mobile-filter-button" onClick={() => setMobileFilters(true)}><MapPin size={16} /> Filters</button><button className="secondary-button" disabled={!result || exporting || busy} onClick={() => { void exportCSV(); }}>{exporting ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />} Export CSV</button></div></section>
      {error && <div className="error-banner" role="alert"><Info size={20} /><div><strong>Analysis needs attention</strong><p>{error}</p>{result && <p>Your previous result is still shown below.</p>}</div><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={18} /></button></div>}
      {selectionChanged && <div className="selection-note"><Info size={16} /> Selection changed. Run analysis to update the results and export.</div>}
      {previewMode && <div className="selection-note"><Info size={16} /> Live interactive preview · Choose a city or coordinates and a year range, then click Run analysis to update the results.</div>}
      {!result ? <div className="empty-state card"><div className="empty-sun"><Sun size={40} /></div><h2>{busy ? 'Reading decades of weather history…' : 'Your analysis starts here'}</h2><p>{busy ? 'Fetching historical daily temperatures, checking coverage, and detecting consecutive heatwave events.' : 'Choose a city and time range, then run the analysis.'}</p>{busy && <div className="loading-bar"><span /></div>}</div> : <div className={busy ? 'results results-loading' : 'results'} aria-busy={busy}>
        <div className="region-strip"><div><span className="location-icon"><MapPin size={17} /></span><strong>{result.request.region_name}</strong><span className="region-coordinates">{result.request.latitude.toFixed(4)}°, {result.request.longitude.toFixed(4)}°</span></div><div><span>{result.request.start_year}–{result.request.end_year}</span><span className="strip-dot">·</span><span>{result.summary.years_analyzed} complete years</span><span className="cache-pill"><Check size={12} />{result.cache.analysis === 'hit' ? 'Cached analysis' : 'Analysis ready'}</span></div></div>
        <section className="insight-banner"><div className="insight-main"><span className="insight-icon">{percentChange != null && percentChange < 0 ? <ArrowDownRight size={29} /> : <TrendingUp size={29} />}</span><div><p className="eyebrow">WHAT THE DATA SAYS</p><h2>{comparison?.available ? <>{percentChange == null ? `${number(comparison.absolute_change, 1)} more heatwave days per year` : percentChange === 0 ? 'Average heatwave days remained stable' : <><span>{number(Math.abs(percentChange), 1)}%</span> {percentChange > 0 ? 'more' : 'fewer'} heatwave days per year</>}</> : 'A closer look at extreme heat'}</h2><p>{comparison?.available ? `${comparison.early_period}: ${number(comparison.early_mean, 1)} days/year → ${comparison.late_period}: ${number(comparison.late_mean, 1)} days/year` : comparison?.reason}</p></div></div><div className="insight-caveat"><Info size={16} /><span>A descriptive comparison of historical periods.<br />Read the methodology for assumptions and limits.</span></div></section>
        <div className="stats-grid"><StatCard label="Heatwave events" value={number(result.summary.total_events)} detail="Distinct events overlapping the period" icon={<Sun size={19} />} /><StatCard label="Heatwave days" value={number(result.summary.total_heatwave_days)} detail="Consecutive extreme-heat days in the period" icon={<Thermometer size={19} />} /><StatCard label="Longest detected event" value={number(result.summary.longest_event_days)} unit="days" detail={`${number(result.summary.mean_event_duration_days, 1)} days per event on average`} icon={<BarChart3 size={19} />} /><StatCard label="Heat threshold" value={number(result.methodology.threshold_c, 1)} unit="°C" detail={`${result.methodology.percentile}th percentile · 1991–2020 baseline`} icon={<TrendingUp size={19} />} /></div>
        <div className="content-tabs" role="tablist" aria-label="Analysis view">{([{ key: 'overview', title: 'Overview' }, { key: 'annual', title: 'Annual data' }, { key: 'method', title: 'Methodology' }] as const).map(tab => <button key={tab.key} id={`tab-${tab.key}`} role="tab" aria-selected={activeTab === tab.key} aria-controls="analysis-panel" className={activeTab === tab.key ? 'active' : ''} onClick={() => setActiveTab(tab.key)}>{tab.title}</button>)}</div>
        <div id="analysis-panel" role="tabpanel" aria-labelledby={`tab-${activeTab}`} tabIndex={0}>
          {activeTab === 'overview' && <><div className="analysis-grid"><Suspense fallback={<div className="card chart-card chart-placeholder"><LoaderCircle className="spin" /> Loading chart…</div>}><ChartPanel result={result} /></Suspense><div className="side-cards"><section className="card quality-card"><div className="section-heading"><h3>Evidence quality</h3><ShieldCheck size={18} /></div><div className="quality-value">{number(result.quality.coverage_pct, 1)}<span>%</span></div><p>Daily temperature coverage</p><div className="coverage-track"><span style={{ width: `${result.quality.coverage_pct}%` }} /></div><dl><div><dt>Valid observations</dt><dd>{number(result.quality.valid_days)}</dd></div><div><dt>Missing or invalid</dt><dd>{number(result.quality.missing_days)}</dd></div><div><dt>Years used in trends</dt><dd>{result.summary.reliable_years} / {result.summary.years_analyzed}</dd></div></dl><p className="quality-note"><Check size={14} /> {result.quality.missing_days ? 'Gaps are retained and disclosed' : 'No missing days in this period'}</p></section><section className="card trend-card"><p className="eyebrow">DIRECTION OF CHANGE</p><h3>{dayTrend?.available ? `${(dayTrend.slope_per_decade ?? 0) >= 0 ? '+' : ''}${number(dayTrend.slope_per_decade, 2)}` : '—'} <span>days / decade</span></h3><p>Linear trend in annual heatwave days</p><div className="trend-meta">{dayTrend?.available ? <>R² {number(dayTrend.r_squared, 2)} <span>·</span> {dayTrend.years_used} years</> : dayTrend?.reason}</div><p className="footnote">A slope measures direction. It is not a significance test.</p></section></div></div>
          <section className="card events-card"><div className="section-heading"><div><p className="eyebrow">THE EVENTS BEHIND THE TREND</p><h2>Heatwave event log</h2></div><span className="subtle">Most recent first · {result.events.length} events</span></div>{displayedEvents.length ? <div className="event-list">{displayedEvents.map(e => <article key={e.start_date} className="event-row"><span className="event-sun"><Sun size={17} /></span><div className="event-dates"><strong>{dateLabel(e.start_date)}</strong><span>through {dateLabel(e.end_date)}</span></div><span className="duration-pill">{e.duration_days} days</span><div className="event-peak"><strong>{number(e.peak_temperature_c, 1)} °C</strong><span>peak temperature</span></div><div className="event-intensity"><strong>+{number(e.mean_exceedance_c, 2)} °C</strong><span>mean above threshold</span></div></article>)}</div> : <div className="no-events"><Sun size={24} /><p>No heatwaves meet this definition in the selected period. Try a longer time range or a different location.</p></div>}{result.events.length > 6 && <div className="pagination"><span>Showing {eventsPage * 6 + 1}–{Math.min((eventsPage + 1) * 6, result.events.length)} of {result.events.length}</span><div><button disabled={eventsPage === 0} onClick={() => setEventsPage(p => p - 1)}>Previous</button><button disabled={(eventsPage + 1) * 6 >= result.events.length} onClick={() => setEventsPage(p => p + 1)}>Next</button></div></div>}</section></>}
          {activeTab === 'annual' && <AnnualTable result={result} />}
          {activeTab === 'method' && <Methodology result={result} />}
        </div>
        <div className="insights-list">{result.insights.slice(1).map(insight => <p key={insight}><Info size={15} />{insight}</p>)}</div>
        <footer className="results-footer"><span>{result.source.attribution}</span><div><button className="text-link" onClick={() => window.print()}>Print / save PDF <ArrowUpRight size={13} /></button><a href={`${apiBase}/api/docs`} target="_blank" rel="noreferrer" className="text-link">API documentation <ArrowUpRight size={13} /></a></div></footer>
      </div>}
      <footer className="page-footer"><span>Climate Lens</span><p>Historical evidence, with its assumptions in view.</p></footer>
    </main>
  </div>;
}
