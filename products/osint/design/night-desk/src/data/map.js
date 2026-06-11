// Mirrors article_locations (lat/lng + district) + per-district sentiment.
// Coordinates are approximate Telangana district centroids for the marker layer.
export const INDIA_TOPO = 'https://cdn.jsdelivr.net/gh/deldersveld/topojson@master/countries/india/india-states.json';

// project window centered on Telangana
export const MAP_CONFIG = { center: [79.0, 17.9], scale: 2600 };

export const DISTRICTS = [
  { id: 'hyd', name: 'Hyderabad', lat: 17.385, lng: 78.4867, sentiment: -0.06, n: 980 },
  { id: 'jangaon', name: 'Jangaon', lat: 17.7236, lng: 79.1779, sentiment: -0.41, n: 142 },
  { id: 'warangal', name: 'Warangal', lat: 17.9689, lng: 79.5941, sentiment: -0.18, n: 268 },
  { id: 'khammam', name: 'Khammam', lat: 17.2473, lng: 80.1514, sentiment: 0.14, n: 110 },
  { id: 'karimnagar', name: 'Karimnagar', lat: 18.4386, lng: 79.1288, sentiment: -0.09, n: 176 },
  { id: 'nizamabad', name: 'Nizamabad', lat: 18.6725, lng: 78.0941, sentiment: 0.05, n: 132 },
  { id: 'nalgonda', name: 'Nalgonda', lat: 17.0575, lng: 79.2684, sentiment: -0.12, n: 154 },
  { id: 'adilabad', name: 'Adilabad', lat: 19.6641, lng: 78.532, sentiment: 0.02, n: 88 },
  { id: 'mahbubnagar', name: 'Mahbubnagar', lat: 16.7375, lng: 77.9974, sentiment: 0.09, n: 121 },
  { id: 'siddipet', name: 'Siddipet', lat: 18.1018, lng: 78.852, sentiment: -0.22, n: 134 },
];

export const TOP_STORIES_BY_DISTRICT = {
  jangaon: 'Arrests of 3 BRS leaders — “suppression” narrative',
  hyd: 'T-Wallet data-security notice from HC',
  khammam: 'Grain procurement reviews welcomed by farmers',
  warangal: 'Irrigation funds cleared by Centre',
};
