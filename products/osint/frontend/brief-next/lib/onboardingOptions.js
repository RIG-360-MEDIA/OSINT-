// Onboarding wizard option lists — GROUNDED in the live corpus (queried 2026-05-29).
// These are stable enums kept static; outlets are fetched live from
// /api/onboarding/sources because there are 200+ and they change.

// Real distinct topic_category values on public.articles (OTHER omitted — it's the catch-all).
export const TOPIC_CATEGORIES = [
  { id: 'POLITICS', label: 'Politics' },
  { id: 'SECURITY', label: 'Security & Defence' },
  { id: 'LEGAL', label: 'Legal & Courts' },
  { id: 'GOVERNANCE', label: 'Governance & Policy' },
  { id: 'FINANCE', label: 'Finance & Markets' },
  { id: 'BUSINESS', label: 'Business' },
  { id: 'INFRASTRUCTURE', label: 'Infrastructure' },
  { id: 'AGRICULTURE', label: 'Agriculture' },
  { id: 'HEALTH', label: 'Health' },
  { id: 'SOCIAL', label: 'Social & Welfare' },
  { id: 'ENVIRONMENT', label: 'Environment' },
  { id: 'TECHNOLOGY', label: 'Technology' },
  { id: 'INTERNATIONAL', label: 'International' },
  { id: 'SPORTS', label: 'Sports' },
];

// Real language_iso volumes: en 79k, te 14k, kn 3.7k, hi 2.4k dominate; rest are thin tails.
export const LANGUAGES = [
  { iso: 'en', label: 'English', note: 'widest coverage' },
  { iso: 'te', label: 'Telugu' },
  { iso: 'kn', label: 'Kannada' },
  { iso: 'hi', label: 'Hindi' },
  { iso: 'mr', label: 'Marathi', note: 'limited' },
  { iso: 'ur', label: 'Urdu', note: 'limited' },
  { iso: 'ne', label: 'Nepali', note: 'limited' },
];

export const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
  'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
  'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
  'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan',
  'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh',
  'Uttarakhand', 'West Bengal', 'Jammu & Kashmir', 'Ladakh', 'Puducherry',
  'Chandigarh', 'Andaman & Nicobar',
];

// source_country ISO2 with real coverage in the corpus.
export const COUNTRIES = [
  { code: 'IN', label: 'India' },
  { code: 'US', label: 'United States' },
  { code: 'GB', label: 'United Kingdom' },
  { code: 'CN', label: 'China' },
  { code: 'PK', label: 'Pakistan' },
  { code: 'NG', label: 'Nigeria' },
  { code: 'AU', label: 'Australia' },
  { code: 'GH', label: 'Ghana' },
  { code: 'LK', label: 'Sri Lanka' },
  { code: 'ZA', label: 'South Africa' },
  { code: 'KE', label: 'Kenya' },
];

export const EVENT_TYPES = [
  { id: 'election', label: 'Elections & campaigns' },
  { id: 'court', label: 'Court verdicts & hearings' },
  { id: 'cabinet', label: 'Cabinet & policy decisions' },
  { id: 'legislation', label: 'Bills & legislation' },
  { id: 'protest', label: 'Protests & agitations' },
  { id: 'scandal', label: 'Scandals & investigations' },
  { id: 'appointment', label: 'Appointments & transfers' },
  { id: 'diplomacy', label: 'Diplomacy & foreign affairs' },
  { id: 'economy', label: 'Economic announcements' },
  { id: 'security', label: 'Security incidents' },
];

export const PURPOSE_OPTIONS = [
  { id: 'monitor_self', label: 'Monitor coverage of my principal/org' },
  { id: 'competitive', label: 'Track rivals & opposition' },
  { id: 'policy', label: 'Follow policy & governance' },
  { id: 'media_intel', label: 'Media & narrative intelligence' },
  { id: 'research', label: 'Research & analysis' },
];

export const LLM_TONE = [
  { id: 'neutral', label: 'Neutral / factual' },
  { id: 'analytical', label: 'Analytical' },
  { id: 'punchy', label: 'Punchy / brief' },
];

export const STANCE_TOWARD = [
  { id: 'supportive', label: 'Favourable' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'critical', label: 'Critical / scrutiny' },
];

export const READING_DEPTH = [
  { id: 'headlines', label: 'Headlines only' },
  { id: 'standard', label: 'Standard' },
  { id: 'deep', label: 'Deep dive' },
];

export const BRIEF_VOICE = [
  { id: 'formal', label: 'Formal' },
  { id: 'conversational', label: 'Conversational' },
  { id: 'terse', label: 'Terse' },
];

export const DENSITY = [
  { id: 'compact', label: 'Compact' },
  { id: 'comfortable', label: 'Comfortable' },
];

export const TIMEZONES = [
  'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Europe/London', 'America/New_York',
];
