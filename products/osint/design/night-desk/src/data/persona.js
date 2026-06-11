// Hardcoded persona — mirrors analytics.user_brief_prefs (primary_subject + watchlist).
// Swap this object for a fetched prefs payload when wiring to the backend.
// Primary subject = the Government of Telangana (org), with Revanth Reddy as its CM/face.
// On wiring, primary_subject_id → the Telangana-Govt entity; `person` is the associated head.
export const SUBJECT = {
  first: 'Telangana',
  last: 'Government',
  person: 'Revanth Reddy',
  role: 'Chief Minister',
  party: 'Indian National Congress',
  state: 'Telangana',
  window: '21-DAY WINDOW',
  windowHours: 504,
  confidence: 'HIGH',
  asOf: 'AS OF 01 JUN 2026 · 06:00 IST',
  clock: 'replay clock',
};

export const OPPOSITION = ['K. Chandrashekar Rao', 'K. T. Rama Rao', 'Bharatiya Janata Party', 'Harish Rao'];
