// The datasets the board is made of. One definition feeds the grids, the charts, the Studio data sources and the
// chat tool schemas, so a field cannot exist in one place only.
const f = (type, label, extra = {}) => ({ type, label, ...extra });

export const DATASETS = {
  reports: {
    label: 'MAUDE reports', noun: 'report', idField: 'id',
    fields: {
      id: f('string', 'Row'), finding: f('string', 'Finding'), report: f('string', 'Report'), received: f('string', 'Received'),
      type: f('string', 'Type', { enum: ['Death', 'Injury', 'Malfunction'] }),
      device: f('string', 'Device'), lot: f('string', 'Lot'), returned: f('string', 'Device returned'), problem: f('string', 'Problem'),
      origin: f('string', 'Source', { enum: ['fda'] }), ts: f('date', 'Time'), day: f('string', 'Day'),
    },
  },
  tallies: {
    label: 'Counts', noun: 'count', idField: 'id',
    fields: {
      id: f('string', 'Row'), finding: f('string', 'Finding'), label: f('string', 'Group'), value: f('number', 'Reports'),
      origin: f('string', 'Source', { enum: ['fda'] }), ts: f('date', 'Time'), day: f('string', 'Day'),
    },
  },
  codes: {
    label: 'Product codes', noun: 'code', idField: 'id',
    fields: {
      id: f('string', 'Row'), finding: f('string', 'Finding'), code: f('string', 'Product code'),
      deaths: f('number', 'Deaths'), injuries: f('number', 'Injuries'), malfunctions: f('number', 'Malfunctions'),
      regulation: f('string', 'Regulation'), origin: f('string', 'Source', { enum: ['fda'] }), ts: f('date', 'Time'), day: f('string', 'Day'),
    },
  },
};
export const DATASET_IDS = Object.keys(DATASETS);
export const fieldIds = (dataset) => Object.keys(DATASETS[dataset]?.fields || {});

/** One-line schema the model sees: dataset, fields and enums, nothing about rows. */
export function schemaText() {
  return DATASET_IDS.map((d) => {
    const fs = Object.entries(DATASETS[d].fields).map(([k, v]) => `${k}:${v.type}${v.enum ? `{${v.enum.join('|')}}` : ''}`).join(', ');
    return `${d}: ${fs}`;
  }).join('\n');
}

/** Derived columns shared by server and browser. Pure; returns new arrays. */
export function prepare(raw, asOf) {
  const out = { asOf, asOfMs: Date.parse(asOf) };
  for (const d of DATASET_IDS) out[d] = (raw[d] || []).map((r) => ({ ...r }));
  return out;
}
