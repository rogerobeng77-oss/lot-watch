import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { prepare } from '../../shared/datasets.mjs';
import { boardPages } from '../../shared/widgets.mjs';
import { getBoard, getData, postScan, getRun, setFindingStatus } from './api.js';
import { Board } from './board.jsx';
import { setMode } from './theme.js';
import { dt, SEVERITY } from './format.js';
import { narrate } from './narrate.js';
import { TrailDialog, DetailsDialog } from './Dialogs.jsx';
import { Icon } from './Icon.jsx';
import { FindingHeader } from './FindingHeader.jsx';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const toDoc = (b) => ({ findings: Object.fromEntries(b.findings.map((f) => [f.id, f])), widgets: Object.fromEntries(b.widgets.map((w) => [w.id, w])) });

function useNarrow() {
  const q = '(max-width: 899px)';
  const [m, setM] = useState(() => window.matchMedia(q).matches);
  useEffect(() => { const mq = window.matchMedia(q); const h = () => setM(mq.matches); mq.addEventListener('change', h); return () => mq.removeEventListener('change', h); }, []);
  return m;
}

export default function App({ initialTheme }) {
  const hostRef = useRef(null);
  const [load, setLoad] = useState({ state: 'loading' });
  const [board, setBoard] = useState(null);
  const [asOf, setAsOf] = useState(null);
  const [page, setPage] = useState('overview');
  const [theme, setTheme] = useState(initialTheme);
  const [data, setData] = useState(null);
  const [run, setRun] = useState(null);
  const [scan, setScan] = useState({ running: false, message: '', error: false, steps: [] });
  const [trailOpen, setTrailOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const narrow = useNarrow();
  const [sevFilter, setSevFilter] = useState(null);
  const [unreviewed, setUnreviewed] = useState(false);
  const [briefH] = useState(21);
  const [trailH, setTrailH] = useState(12);
  const liveRef = useRef(null);

  const refresh = useCallback(async ({ withData = true } = {}) => {
    const [b, d] = await Promise.all([getBoard(), withData ? getData() : null]);
    setBoard({ ...b, doc: toDoc(b) });
    setAsOf(b.asOf);
    if (d) setData(prepare(d.rows, d.asOf));
    return b;
  }, []);

  const setStatus = useCallback(async (id, status) => {
    try { await setFindingStatus(id, status); await refresh({ withData: false }); } catch (e) { setScan((s) => ({ ...s, message: e.message, error: true })); }
  }, [refresh]);

  useEffect(() => {
    refresh().then(() => setLoad({ state: 'ready' })).catch((e) => { console.error(e); setLoad({ state: 'error', message: e.message }); });
    const timer = setInterval(() => { if (document.visibilityState === 'visible') refresh().catch(() => {}); }, 60000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => { setMode(theme); try { localStorage.setItem('tw-theme', theme); } catch { /* storage blocked */ } }, [theme]);

  const only = useMemo(() => (sevFilter || unreviewed ? (f) => (!sevFilter || f.severity === sevFilter) && (!unreviewed || f.status === 'open') : null), [sevFilter, unreviewed]);
  // The scan trail takes the height the cards leave, so the Overview never ends in blank space.
  useEffect(() => {
    const el = hostRef.current; if (!el || narrow) return undefined;
    const n = board ? Math.max(1, Math.ceil(Object.values(board.doc.findings).filter((f) => f.status !== 'dismissed' && (!only || only(f))).length / 2)) : 2;
    const calc = () => setTrailH(Math.max(10, Math.floor((el.clientHeight - 64) / 16) - n * briefH));
    calc(); const ro = new ResizeObserver(calc); ro.observe(el); return () => ro.disconnect();
  }, [board, narrow, only, load.state, briefH]);
  // The latest run feeds the trail widget on the Overview.
  const lastRunId = board?.runs?.[0]?.id;
  useEffect(() => { if (!lastRunId) return; getRun(lastRunId).then(setRun).catch(() => {}); }, [lastRunId]);

  const pages = useMemo(() => (board ? boardPages(board.doc) : { pages: [], findings: [] }), [board]);
  const current = pages.pages.find((p) => p.id === page) || pages.pages[0];
  const windowLabel = asOf ? `${new Date(Date.parse(asOf) - 29 * 86400000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })} to ${new Date(asOf).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}` : '';
  const finding = current?.findingId ? board.doc.findings[current.findingId] : null;
  useEffect(() => { if (board && !pages.pages.some((p) => p.id === page)) setPage('overview'); }, [board, pages, page]);

  const announce = (msg) => { if (liveRef.current) liveRef.current.textContent = msg; };

  async function runScan() {
    if (scan.running) return;
    setScan({ running: true, message: 'Starting the read.', error: false, steps: [] });
    try {
      const { runId } = await postScan(false);
      let run;
      for (let i = 0; i < 160; i++) {
        await sleep(i < 2 ? 1200 : 2500);
        run = await getRun(runId);
        const last = run.steps[run.steps.length - 1];
        setScan((s) => ({ ...s, steps: run.steps, message: narrate(last) }));
        if (run.done) break;
      }
      if (!run?.done) throw new Error('The read is still running. Open the agent trail to follow it, then reload.');
      if (run.error) throw new Error(run.error);
      await refresh();
      const msg = run.summary ? run.summary.split('\n').filter(Boolean).slice(-1)[0] : 'Read finished.';
      setScan({ running: false, message: `${run.fallback ? 'Done, with rule-built findings: ' + run.fallback + ' ' : ''}${msg}`.trim(), error: false, steps: run.steps, done: true });
      announce(`Read finished. ${pages.findings.length} findings on the board.`);
    } catch (e) {
      setScan({ running: false, message: e.status === 429 ? 'Live reads are used up for now. The cached findings still work.' : `${e.message}`, error: true, steps: [] });
    }
  }

  if (load.state === 'error') {
    return <main className="empty" role="alert"><h2>Unable to load the board</h2><p>{load.message}</p><p><button className="tw-btn tw-btn-primary" onClick={() => location.reload()}>Reload</button></p></main>;
  }

  const nOpen = pages.findings.filter((f) => f.status === 'open').length;
  return (
    <div className="app">
      <a className="skip" href="#board">Skip to the board</a>
      <header className="topbar">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="var(--steel)" /><path d="M5 25h10l5-11 5 15 4-8h6" fill="none" stroke="var(--onSteel)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx="20" cy="14" r="4" fill="var(--signalFill)" /></svg>
          <div><div className="brand-name">Lot Watch</div><div className="brand-sub">FDA stapler reports, read in full</div></div>
        </div>
        {asOf && <div className="clock" title="Latest openFDA MAUDE pull in this board."><span>FDA data to</span><b>{dt(asOf)}</b></div>}
        <button type="button" className="tw-btn tw-btn-primary has-icon" onClick={runScan} disabled={scan.running || load.state !== 'ready'}>
          <Icon name={scan.running ? 'spin' : 'scan'} /><span className="btn-label">{scan.running ? 'Reading' : 'Read the reports'}</span>
        </button>
        <button type="button" className="tw-btn has-icon" onClick={() => setDetailsOpen(true)}><Icon name="info" /><span className="btn-label">Details</span></button>
        <button type="button" className="tw-btn has-icon" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} aria-label={theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
      </header>

      <div className={`statusline ${scan.error ? 'is-error' : ''}`} hidden={!scan.message && !scan.running} role="status">
        <p>{scan.message}</p>
        {scan.steps.length > 0 && <button type="button" onClick={() => setTrailOpen(true)}>Agent trail</button>}
        {!scan.running && <button type="button" onClick={() => setScan({ running: false, message: '', error: false, steps: [] })}>Dismiss</button>}
      </div>
      <div className="tw-sr" aria-live="polite" ref={liveRef} />

      <div className="main">
        <nav className="rail" aria-label="Board">
          {!finding ? (
            <>
              <div className="rail-h">Show</div>
              <div className="filters" role="group" aria-label="Filter findings">
                {['high', 'medium', 'low'].map((sv) => {
                  const n = pages.findings.filter((f) => f.severity === sv).length;
                  return <button key={sv} type="button" className="chip" aria-pressed={sevFilter === sv} disabled={!n} onClick={() => setSevFilter(sevFilter === sv ? null : sv)}><span>{SEVERITY[sv].glyph} {SEVERITY[sv].word}</span><span className="c">{n}</span></button>;
                })}
                <button type="button" className="chip" aria-pressed={unreviewed} onClick={() => setUnreviewed((u) => !u)}><span>Unreviewed only</span><span className="c">{nOpen}</span></button>
              </div>
              <div className="rail-h">Reports</div>
              <dl className="sum">
                <dt>Span</dt><dd>{board?.span || windowLabel}</dd>
                <dt>Findings</dt><dd>{pages.findings.length}</dd>
                <dt>Reviewed</dt><dd>{pages.findings.filter((f) => f.status === 'reviewed').length}</dd>
                <dt>Written by</dt><dd>{pages.findings.some((f) => f.author === 'rules') ? 'agent + rules' : 'the agent'}</dd>
              </dl>
            </>
          ) : (
            <>
              <button type="button" className="link" onClick={() => setPage('overview')}>All findings</button>
              <div className="rail-h">Jump to</div>
              <ul className="nav jump">
                {pages.findings.map((f) => (
                  <li key={f.id}><button type="button" className={`nav-item ${f.status !== 'open' ? 'is-done' : ''}`} aria-current={current?.id === f.id ? 'page' : undefined} onClick={() => setPage(f.id)}>
                    <span className="t">{f.title}</span></button></li>
                ))}
              </ul>
            </>
          )}
          <div className="rail-foot">
            <button type="button" className="link" onClick={() => setTrailOpen(true)} disabled={!board?.runs?.length}>Agent trail for the last read</button>
            <p className="rail-note">{board?.runs?.[0] ? `Last read ${dt(board.runs[0].startedAt)} · ${board.runs[0].fallback ? 'rules fallback used' : 'written by the agent'}` : 'No scan yet.'}</p>
          </div>
        </nav>

        <section className="stage" id="board" aria-label={current?.title || 'Board'}>
          {finding ? <FindingHeader f={finding} onStatus={setStatus} /> : (
            <div className="stage-bar"><h1>{finding ? finding.title : (board?.findings?.length
              ? `${(board?.findings || []).filter((f) => f.severity === 'high').length} of ${(board?.findings || []).length} findings need an answer today.`
              : 'Nothing flagged in these reports.')}</h1></div>
          )}
          <div className="studio-wrap">
            <div className="studio-host" ref={hostRef}>{load.state === 'ready' && board && <Board doc={board.doc} page={current?.id || 'overview'} data={data} mode={theme} run={run} stack={narrow} briefH={briefH} only={only} trailH={trailH} onOpen={setPage} onStatus={setStatus} />}</div>
            {load.state === 'loading' && <div className="empty"><h2>Loading the reports</h2><p>Reading findings and widgets.</p></div>}
          </div>
        </section>
      </div>

      <TrailDialog open={trailOpen} onClose={() => setTrailOpen(false)} runs={board?.runs || []} live={scan.running ? scan.steps : null} />
      <DetailsDialog open={detailsOpen} onClose={() => setDetailsOpen(false)} />
    </div>
  );
}
