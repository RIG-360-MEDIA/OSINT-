// Telangana scope configuration. Edit channel IDs / RSS URLs here without
// touching the briefing component.

export const TELANGANA = {
  // Hyderabad coordinates (state capital, used for weather + AQI center)
  lat: 17.385,
  lon: 78.4867,
  tz: 'Asia/Kolkata',

  // Display strings
  name: 'Telangana',
  capital: 'Hyderabad',
  locale: 'en-IN',
} as const

// YouTube live channels (Telugu news). The embed URL pattern for a channel's
// live stream is:
//   https://www.youtube.com/embed/live_stream?channel=<CHANNEL_ID>
// If a channel isn't currently live, YouTube renders the channel's most-recent
// video, which is the desired fallback.
// Channel IDs scraped from each channel's @handle page on 2026-04-27 and
// verified to return a live_stream embed (not "video unavailable").
export const TELUGU_LIVE_CHANNELS = [
  { id: 'UCDCMjD1XIAsCZsYHNMGVcog', label: 'V6 News' },
  { id: 'UCPXTXMecYqnRKNdqdVOGSFg', label: 'TV9 Telugu' },
  { id: 'UCk0XiSICe9O0YO8oNFVpPAA', label: 'T News' },
  { id: 'UC_2irx_BQR7RsBKmUV9fePQ', label: 'ABN Telugu' },
  { id: 'UCfymZbh17_3T_UhgjkQ9fRQ', label: '10TV Telugu' },
  { id: 'UCZ9m4KOh8Ei60428xeGYDCQ', label: 'Sakshi TV' },
  { id: 'UC-PPlFHLfi4wcFOe6DrReCQ', label: 'News18 Telugu' },
  { id: 'UCAR3h_9fLV82N2FH4cE4RKw', label: 'TV5 News' },
  { id: 'UCumtYpCY26F6Jr3satUgMvA', label: 'NTV Telugu' },
] as const

// Telangana / Hyderabad RSS sources. Fetched server-side to avoid CORS;
// see backend router for the proxy endpoint.
export const TELANGANA_RSS = [
  { id: 'thehindu-hyd', label: 'The Hindu — Hyderabad', url: 'https://www.thehindu.com/news/cities/Hyderabad/feeder/default.rss' },
  { id: 'dc-hyd', label: 'Deccan Chronicle — Hyderabad', url: 'https://www.deccanchronicle.com/rss/section/cities/hyderabad' },
  { id: 'tg-today', label: 'Telangana Today', url: 'https://www.telanganatoday.com/feed' },
  { id: 'siasat-hyd', label: 'Siasat — Hyderabad', url: 'https://www.siasat.com/feed/' },
] as const

// Stability-index weights. Each sub-signal is normalized 0..1 (1 = perfectly
// calm) and weighted; final score is rounded to integer 0..100.
export const STABILITY_WEIGHTS = {
  airQuality: 0.30,    // higher AQI = lower score
  heatStress: 0.25,    // closer to 45°C = lower score
  conflictEvents: 0.25, // ACLED count past 7d
  newsAnomaly: 0.20,   // anomalous keyword density (set 1.0 until LLM scoring lands)
} as const
