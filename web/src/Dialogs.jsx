import React, { useEffect, useRef, useState } from 'react';
import { getRun, getDiagnostics } from './api.js';
import { narrate } from './narrate.js';
import { dt, int } from './format.js';
import { Icon } from './Icon.jsx';
import { DATASETS } from '../../shared/datasets.mjs';

function useDialog(open, onClose) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current; if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => { const d = ref.current; const h = () => onClose(); d?.addEventListener('close', h); return () => d?.removeEventListener('close', h); }, [onClose]);
  return ref;
}

const KIND = { model: 'Agent', tool: 'Tool', fallback: 'Fallback', retry: 'Retry', note: 'Note', error: 'Error' };

export function TrailDialog({ open, onClose, runs, live }) {
  const ref = useDialog(open, onClose);
  const [run, setRun] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    if (!open) return;
    if (live) { setRun({ id: 'live', steps: live, done: false }); return; }
    if (!runs[0]) { setRun(null); return; }
    setErr('');
    getRun(runs[0].id).then(setRun).catch((e) => setErr(e.message));
  }, [open, runs, live]);
  return (
    <dialog ref={ref} aria-labelledby="trail-h" onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="dlg-h"><h2 id="trail-h">Agent trail</h2><button type="button" className="tw-btn has-icon" onClick={onClose} aria-label="Close the agent trail"><Icon name="close" /></button></div>
      <div className="dlg-b">
        {err && <p role="alert">{err}</p>}
        {!run && !err && <p className="muted">No read has run yet. Press Read the reports.</p>}
        {run && (
          <>
            <dl className="kv">
              <dt>Started</dt><dd>{run.startedAt ? dt(run.startedAt) : 'Now'} · {run.trigger || 'manual'}</dd>
              <dt>Model</dt><dd>{run.model || 'Not used in this run'}{run.usage?.calls ? ` · ${run.usage.calls} requests${run.usage.input ? `, ${int(run.usage.input)} tokens in, ${int(run.usage.output)} out` : ''}` : ''}</dd>
              {run.fallback && <><dt>Fallback</dt><dd>{run.fallback}</dd></>}
              {run.summary && <><dt>Result</dt><dd>{run.summary}</dd></>}
            </dl>
            <ol className="trail">
              {(run.steps || []).map((s, i) => (
                <li key={i}>
                  <span className={`k ${s.kind === 'error' ? 'err' : ''}`}>{KIND[s.kind] || s.kind}{s.tool ? ` · ${s.tool}` : ''}</span>
                  <div>
                    <div className="txt">{narrate(s)}</div>
                    {s.kind === 'tool' && <details><summary>Show the call</summary><pre>{JSON.stringify({ input: s.input, result: typeof s.detail === 'string' ? safe(s.detail) : s.detail }, null, 2)}</pre></details>}
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </dialog>
  );
}
const safe = (s) => { try { return JSON.parse(s); } catch { return s; } };

export function DetailsDialog({ open, onClose }) {
  const ref = useDialog(open, onClose);
  const [d, setD] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => { if (!open) return; setErr(''); getDiagnostics().then(setD).catch((e) => setErr(e.message)); }, [open]);

  return (
    <dialog ref={ref} aria-labelledby="det-h" onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="dlg-h"><h2 id="det-h">Details</h2><button type="button" className="tw-btn has-icon" onClick={onClose} aria-label="Close the details"><Icon name="close" /></button></div>
      <div className="dlg-b">
        {err && <p role="alert">{err}</p>}
        <section>
          <h3>What the board is made of</h3>
          {d ? <table className="tbl"><thead><tr><th>Dataset</th><th className="n">Rows</th></tr></thead><tbody>
            {Object.entries(d.counts).map(([k, v]) => <tr key={k}><td>{DATASETS[k].label}</td><td className="n">{int(v)}</td></tr>)}
          </tbody></table> : <p className="muted">Loading.</p>}
        </section>
        <section>
          <h3>Source</h3>
          <p>{d?.asOf ? `openFDA device event reports, pulled ${dt(d.asOf)}. ` : ''}Reports are unvalidated and carry no denominator, so counts here are counts, never rates.</p>
        </section>
        <section>
          <h3>Models</h3>
          <p>{d?.model || 'NVIDIA Nemotron on Nebius Token Factory'}: Nano reads each narrative, Super writes the finding text. Findings are cached; Read the reports runs one live Nano read.</p>
          <p>AG Grid Community and AG Charts Community, both MIT licensed.</p>
        </section>
      </div>
    </dialog>
  );
}
