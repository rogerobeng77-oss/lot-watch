// The board: findings as cards, evidence as an AG Grid (Community), breakdowns as AG Charts (Community). Read-only.
import React, { useMemo, useRef, useState, useCallback } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AgCharts } from 'ag-charts-react';
import { toStudioState } from '../../shared/widgets.mjs';
import { DATASETS } from '../../shared/datasets.mjs';
import { breakdown, matches } from '../../shared/metrics.mjs';
import { gridTheme, chartTheme, tok } from './theme.js';
import { SEVERITY, KIND, STATUS_WORDS, STATUS_TONE, TONE_GLYPH, sentence, dtDay, dt, int, pct, midTrunc, trunc, plural, gapRows } from './format.js';
import { narrate } from './narrate.js';

const OPFN = { eq: (a, b) => a === b, ne: (a, b) => a !== b, gt: (a, b) => a > b, gte: (a, b) => a >= b, lt: (a, b) => a < b, lte: (a, b) => a <= b, in: (a, b) => Array.isArray(b) && b.includes(a) };

export function Gap({ gap }) {
  const rows = gapRows(gap);
  if (!rows.length) return null;
  return (
    <div className="gap" role="img" aria-label={rows.map((g) => `${g.label} ${g.text}`).join(' versus ')}>
      {rows.map((g) => <div key={g.label} className={`gap-row ${g.real ? 'is-real' : ''}`}><span className="gap-l">{g.label}</span><span className="gap-track"><span className="gap-fill" style={{ width: `${g.pct}%` }} /></span><span className="gap-v">{g.text}</span></div>)}
    </div>
  );
}

function Brief({ f, onOpen, onStatus }) {
  if (!f) return <section className="tw-widget"><p className="tw-empty">This finding is no longer on the board.</p></section>;
  const sev = SEVERITY[f.severity] || SEVERITY.low;
  const reviewed = f.status === 'reviewed';
  return (
    <section className={`tw-widget tw-brief-w sev-${f.severity} is-compact ${reviewed ? 'is-done' : ''}`} aria-label={`${f.title}. ${sev.word} severity.`}>
      <div className="tw-brief-top">
        <span className="tw-sev"><span aria-hidden="true">{sev.glyph}</span> {sev.word}</span>
        <span className="tw-kind">{KIND[f.kind] || f.kind}</span>
        {reviewed && <span className="tw-badge">Reviewed</span>}
      </div>
      <h3 className="tw-brief-title">{f.title}</h3>
      <p className="tw-headline">{f.headline}</p>
      <Gap gap={f.gap} />
      {f.brief && <p className="tw-summary">{f.brief}</p>}
      <footer className="tw-brief-foot">
        <button type="button" className="tw-btn tw-btn-primary" onClick={() => onOpen(f.id)}>Open the board</button>
        <button type="button" className="tw-btn" aria-pressed={reviewed} onClick={() => onStatus(f.id, reviewed ? 'open' : 'reviewed')}>{reviewed ? 'Reopen' : 'Mark reviewed'}</button>
        <span className="tw-meta">{plural(f.evidenceIds?.length || 0, 'row', 'rows')} flagged · {f.window?.label} · to {dtDay(f.window?.to)}</span>
      </footer>
    </section>
  );
}

function Head({ title }) { return <header className="tw-wh"><h3 className="tw-wt">{title}</h3></header>; }

function Pill({ status }) {
  const tone = STATUS_TONE[status] || 'info';
  return <span className={`tw-pill tw-pill-${tone}`}><span aria-hidden="true">{TONE_GLYPH[tone]}</span> {STATUS_WORDS[status] || sentence(status)}</span>;
}

function Bar({ value, max }) {
  return <span className="tw-agebar"><span className="tw-agebar-fill" style={{ width: `${max ? Math.min(100, (value / max) * 100) : 0}%` }} /><span className="tw-agebar-n">{value}</span></span>;
}

function EvidenceGrid({ rec, data }) {
  const spec = rec.spec, ds = DATASETS[spec.dataset];
  const api = useRef(null);
  const [q, setQ] = useState('');
  const [shown, setShown] = useState({ n: 0, deaths: 0 });
  const rows = useMemo(() => (data ? data[spec.dataset].filter((r) => matches(r, spec.where)) : []), [data, spec]);
  const columnDefs = useMemo(() => {
    const hl = new Set(spec.highlight || []);
    const maxOf = (field) => Math.max(0, ...rows.map((r) => Number(r[field]) || 0));
    const cols = spec.columns.map((c) => {
      const f = ds.fields[c.field];
      const def = { field: c.field, headerName: c.header || f.label, minWidth: Math.max(c.width || 0, f.type === 'number' ? 120 : c.renderer === 'status' ? 120 : 110), sortable: true, resizable: true, suppressHeaderMenuButton: true, flex: 1, type: f.type === 'number' ? 'numericColumn' : undefined, cellClass: f.type === 'number' ? 'tw-num' : undefined };
      if (c.renderer === 'status') def.cellRenderer = (p) => (p.value ? <Pill status={p.value} /> : null);
      if (c.renderer === 'bar') { const m = maxOf(c.field); def.cellRenderer = (p) => (typeof p.value === 'number' ? <Bar value={p.value} max={m} /> : p.value ?? null); }
      if (c.field === 'problem') { def.wrapText = true; def.autoHeight = true; def.cellStyle = { lineHeight: '1.35', paddingTop: '4px', paddingBottom: '4px', whiteSpace: 'normal' }; }
      const rules = spec.rules.filter((r) => r.field === c.field);
      if (rules.length) { def.cellClassRules = {}; for (const r of rules) def.cellClassRules[`tw-tone tw-tone-${r.tone}`] = (p) => OPFN[r.op](p.value, r.value); }
      if (spec.sort?.field === c.field) def.sort = spec.sort.dir;
      return def;
    });
    if (hl.size) cols.unshift({ headerName: '', colId: '__flag', width: 52, minWidth: 52, maxWidth: 52, flex: 0, pinned: 'left', sortable: false, resizable: false, suppressHeaderMenuButton: true,
      valueGetter: (p) => (p.data && hl.has(p.data.id) ? 1 : 0),
      cellRenderer: (p) => (p.value ? <span className="tw-flag" role="img" aria-label="Flagged">▲</span> : null) });
    return cols;
  }, [spec, rows, ds]);
  const hl = useMemo(() => new Set(spec.highlight || []), [spec]);
  const count = useCallback(() => {
    let n = 0, deaths = 0;
    api.current?.forEachNodeAfterFilterAndSort((node) => { if (node.data) { n++; if (node.data.type === 'Death') deaths++; } });
    setShown({ n, deaths });
  }, []);
  return (
    <section className="tw-widget tw-grid-w" aria-label={spec.title}>
      <Head title={spec.title} />
      <div className="tw-tools">
        <label className="tw-qf"><span className="tw-sr">Filter rows</span><input type="search" placeholder="Filter rows" autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <button type="button" className="tw-btn" onClick={() => api.current?.resetColumnState()}>Reset columns</button>
        <button type="button" className="tw-btn" onClick={() => api.current?.exportDataAsCsv({ fileName: `${spec.dataset}.csv` })}>Download CSV</button>
      </div>
      <div className="tw-grid-host">
        <AgGridReact theme={gridTheme} rowData={rows} columnDefs={columnDefs} getRowId={(p) => p.data.id} quickFilterText={q}
          defaultColDef={{ sortable: true, resizable: true }} rowClassRules={{ 'tw-row-flagged': (p) => !!p.data && hl.has(p.data.id) }}
          onGridReady={(e) => { api.current = e.api; count(); }} onModelUpdated={count} />
      </div>
      <div className="tw-foot"><span>Rows: {shown.n}</span>{shown.deaths > 0 && <span>{plural(shown.deaths, 'death', 'deaths')}</span>}</div>
    </section>
  );
}

function Breakdown({ rec, data, mode }) {
  const spec = rec.spec, t = tok(mode);
  const options = useMemo(() => {
    if (!data) return null;
    const rows = breakdown(data, spec.dataset, { by: spec.by, where: spec.where, agg: spec.agg, field: spec.field, limit: spec.limit });
    const hl = new Set(spec.highlight || []);
    const total = rows.reduce((s, x) => s + x.value, 0);
    const d = rows.map((r) => ({ key: r.key, label: (hl.has(r.key) ? '▲ ' : '') + trunc(r.key, 22), value: r.value, flagged: hl.has(r.key), share: total ? r.value / total : 0 }));
    const horizontal = spec.chartType === 'bar';
    if (horizontal) d.reverse();
    const fmt = (v) => int(v);
    const max = Math.max(...d.map((r) => r.value));
    const tip = { renderer: (p) => ({ heading: p.datum.key, data: [{ label: spec.agg === 'sum' ? 'Total' : 'Count', value: fmt(p.datum.value) }, { label: 'Share', value: pct(p.datum.share) }] }) };
    return {
      data: d, theme: chartTheme(mode), background: { fill: 'transparent' },
      series: [{ type: 'bar', direction: horizontal ? 'horizontal' : 'vertical', xKey: 'label', yKey: 'value', yName: spec.agg === 'sum' ? 'Total' : 'Count', fill: t.steel, cornerRadius: 3,
        itemStyler: (p) => (p.datum.flagged ? { fill: t.signalFill, stroke: t.signalFill } : {}), label: { enabled: true, color: t.ink, placement: 'outside-end', formatter: (p) => fmt(p.value) }, tooltip: tip }],
      axes: { x: { type: 'category', position: horizontal ? 'left' : 'bottom', label: { avoidCollisions: true }, line: { enabled: true } },
        y: { type: 'number', position: horizontal ? 'bottom' : 'left', min: 0, max: max > 0 ? max * 1.18 : 1, label: { formatter: (p) => fmt(p.value) }, gridLine: { style: [{ stroke: t.grid }] } } },
      legend: { enabled: false }, padding: { top: 10, right: 44, bottom: 6, left: 16 },
    };
  }, [data, spec, mode, t]);
  return (
    <section className="tw-widget tw-chart-w" aria-label={spec.title}>
      <Head title={spec.title} />
      {spec.caption && <p className="tw-caption">{spec.caption}</p>}
      <div className="tw-chart-host" role="img" aria-label={spec.title}>{options && <AgCharts options={options} style={{ height: '100%' }} />}</div>
    </section>
  );
}

const LABEL = { tool: 'Tool', model: 'Agent', note: 'Note', fallback: 'Fallback', retry: 'Retry', error: 'Error' };
function Trail({ run }) {
  if (!run) return <section className="tw-widget tw-trail-w"><p className="tw-empty">No read has run yet. Press Read the reports.</p></section>;
  const steps = (run.steps || []).filter((s) => s.kind !== 'model' || s.detail);
  const tools = steps.filter((s) => s.kind === 'tool');
  const built = tools.filter((s) => s.tool === 'build_widget' && s.ok !== false).length;
  const facts = [`${int(run.usage?.calls || 0)} model requests`, `${tools.length} tool calls`, `${built} widgets built`].join(' · ');
  return (
    <section className="tw-widget tw-trail-w">
      <header className="tw-wh"><h3 className="tw-wt">How this board was built</h3><span className="tw-meta">{dt(run.startedAt)}</span></header>
      <p className="tw-caption">{facts}</p>
      <ol className="tw-trail-list" tabIndex={0} aria-label="Steps of the last read">
        {steps.map((s, i) => <li key={i}><span className={`k ${s.kind === 'error' ? 'err' : ''}`}>{LABEL[s.kind] || s.kind}</span><span>{String(narrate(s)).slice(0, 160)}</span></li>)}
      </ol>
    </section>
  );
}

/** One page of the board, laid out on the same 24-track grid the widget sizes are written for. */
export function Board({ doc, page, data, mode, run, stack, briefH, only, trailH, onOpen, onStatus }) {
  const state = useMemo(() => toStudioState(doc, page, { stack, briefH, only, trailH, stackBriefH: window.innerWidth < 460 ? 33 : window.innerWidth < 640 ? 24 : 17 }), [doc, page, stack, briefH, only, trailH]);
  const pg = state.pages.find((p) => p.id === state.selectedPageId);
  if (!pg) return null;
  return (
    <div className="board">
      {Object.entries(pg.widgets).map(([id, w]) => {
        const l = pg.widgetLayout[id];
        const rec = doc.widgets[id];
        let body = null;
        if (w.type === 'tw-brief') body = <Brief f={doc.findings[id.replace(/^brief-/, '')]} onOpen={onOpen} onStatus={onStatus} />;
        else if (w.type === 'tw-trail') body = <Trail run={run} />;
        else if (rec?.type === 'tw-grid') body = <EvidenceGrid rec={rec} data={data} />;
        else if (rec?.type === 'tw-breakdown') body = <Breakdown rec={rec} data={data} mode={mode} />;
        return <div key={id} className="board-cell" style={{ gridColumn: `${l.xTrack + 1} / span ${l.xSpan}`, gridRow: `${l.yTrack + 1} / span ${l.ySpan}` }}>{body}</div>;
      })}
    </div>
  );
}
