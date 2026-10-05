import React from 'react';
import { SEVERITY, KIND, dtDay, plural } from './format.js';
import { Gap } from './board.jsx';


function splitSummary(t) {
  const sentences = String(t || '').replace(/\s+/g, ' ').trim().match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) || [];
  return { lead: sentences.slice(0, 2).join('').trim(), rest: sentences.slice(2).join('').trim() };
}

export function FindingHeader({ f, onStatus }) {
  const { lead, rest } = splitSummary(f.summary);
  const sev = SEVERITY[f.severity] || SEVERITY.low;
  const reviewed = f.status === 'reviewed';
  return (
    <article className={`fhead sev-${f.severity} ${reviewed || f.status === 'cleared' ? 'is-done' : ''}`}>
      <div className="fhead-main">
        <div className="fhead-tags">
          <span className={`sevtag sev-${f.severity}`}><span className="g" aria-hidden="true">{sev.glyph}</span> {sev.word} severity</span>
          <span className="fhead-kind">{KIND[f.kind] || f.kind}</span>
          {f.status === 'cleared' && <span className="tw-badge">Cleared</span>}
          {reviewed && <span className="tw-badge">Reviewed</span>}
          {f.author === 'rules' && <span className="tw-badge tw-badge-rules" title="A fixed template wrote this from the counts.">Written by rules</span>}
        </div>
        <h1 className="fhead-title">{f.title}</h1>
        <p className="fhead-headline">{f.headline}</p>
        <Gap gap={f.gap} />
        <p className="fhead-summary">{lead}</p>
        {rest && <details className="fhead-more"><summary>Read the rest</summary><p className="fhead-summary">{rest}</p></details>}
        <div className="fhead-foot">
          <button type="button" className="tw-btn" aria-pressed={reviewed} onClick={() => onStatus(f.id, reviewed ? 'open' : 'reviewed')}>{reviewed ? 'Reopen' : 'Mark reviewed'}</button>
          <span className="tw-meta">{plural(f.evidenceIds?.length || 0, 'row', 'rows')} flagged · {f.window?.label} · to {dtDay(f.window?.to)}</span>
        </div>
      </div>
      <aside className="fhead-actions" aria-label="Next steps">
        <h2>Next steps</h2>
        <ol>{(f.actions || []).map((a, i) => <li key={i}>{a}</li>)}</ol>
      </aside>
    </article>
  );
}
