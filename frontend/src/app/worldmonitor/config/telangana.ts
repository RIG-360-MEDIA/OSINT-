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
export const TELUGU_LIVE_CHANNELS = [
  { id: 'UCwGsZ_OkUBP1FiouQ54AWcA', label: 'V6 News' },
  { id: 'UCQ_FATLW83q-4xJ2fsi8qAw', label: 'TV9 Telugu' },
  { id: 'UCqv1rbEJ5wY15SSxLfKPyCQ', label: 'T News' },
  { id: 'UCIuWERA-rEKXvDX-PEVNAmw', label: 'ABN Telugu' },
  { id: 'UCqd9JUdsoQA91TkOyiyMQww', label: '10TV Telugu' },
  { id: 'UCJi7ND-0VGZUIo3-LVT-Y-w', label: 'Sakshi TV' },
  { id: 'UC8HuYwPsAKaaXi0VGD4Ml_w', label: 'HMTV' },
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
