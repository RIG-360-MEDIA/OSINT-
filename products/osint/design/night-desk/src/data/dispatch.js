// Mirrors export.py (render/PDF) + mailer (Gmail) + intel.coverage_qa (pre-send gate)
// + scheduling/archive. Delivery + integrations surface.

export const CHANNELS = [
  { ic: '✉', name: 'Gmail', desc: 'Send the brief to recipients via the Gmail connector', state: 'connected' },
  { ic: '⬇', name: 'PDF one-pager', desc: 'Newspaper-style PDF export', state: 'ready' },
  { ic: '◆', name: 'Newsletter', desc: 'HTML newsletter to a subscriber list', state: 'ready' },
  { ic: '⌬', name: 'MCP server', desc: 'Expose this brief to Claude / agents (read-only)', state: 'beta' },
];

export const SCHEDULE = { cadence: 'Daily · 06:00 IST', next: 'Tomorrow 06:00', recipients: 4 };

export const RECIPIENTS = [
  { name: 'CMO Comms Desk', addr: 'comms@cmo.tg.gov.in' },
  { name: 'Press Secretary', addr: 'press.sec@tg.gov.in' },
  { name: 'War-room (internal)', addr: 'warroom@rig360.in' },
  { name: 'You', addr: 'heretech.shodh1@gmail.com' },
];

export const QA = {
  pass: true,
  checks: [
    { ok: true, t: 'Source diversity: 9 outlets across 3 languages (≥ floor of 5).' },
    { ok: true, t: 'Both stances present: 3 supportive + 4 critical findings (no echo chamber).' },
    { ok: false, t: 'FINANCE under-covered by you (1 vs 119) — flagged, not blocking.' },
    { ok: true, t: 'Every LLM line passed the faithfulness gate (cite-checked).' },
  ],
};

export const ARCHIVE = [
  { date: '31 May 2026', title: 'Two-front offensive; Jangaon flashpoint', opens: '4/4' },
  { date: '30 May 2026', title: 'Procurement counter-move lands', opens: '4/4' },
  { date: '29 May 2026', title: 'T-Wallet data notice breaks', opens: '3/4' },
  { date: '28 May 2026', title: 'BRS “failed farmers” attack originates', opens: '4/4' },
];
