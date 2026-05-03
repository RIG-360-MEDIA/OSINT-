-- seeds/districts_ap.sql
--
-- 26 Andhra Pradesh districts (post-2022 reorganisation). Centroids
-- are approximate HQ-city geocodes — fine for nearest-centroid lookup
-- with the 80km cap that district_for_lat_lon enforces. Aliases
-- include the common spellings and the pre-2022 parent district name.
--
-- Idempotent: ON CONFLICT (id) DO UPDATE so re-running keeps the
-- table in sync without churn on the FK references.

INSERT INTO districts (id, name, hq_city, centroid_lat, centroid_lon, state_code, aliases) VALUES
  ('alluri-sitarama-raju',  'ALLURI SITARAMA RAJU', 'Paderu',          18.0760, 82.6900, 'AP', ARRAY['Visakhapatnam','Paderu']),
  ('anakapalli',            'ANAKAPALLI',           'Anakapalli',      17.6920, 83.0033, 'AP', ARRAY['Anakapalle']),
  ('anantapur',             'ANANTAPUR',            'Anantapur',       14.6820, 77.6000, 'AP', ARRAY['Anantapuramu']),
  ('annamayya',             'ANNAMAYYA',            'Rayachoti',       13.9590, 78.7470, 'AP', ARRAY['Kadapa','Rayachoti']),
  ('bapatla',               'BAPATLA',              'Bapatla',         15.9040, 80.4670, 'AP', ARRAY['Guntur']),
  ('chittoor',              'CHITTOOR',             'Chittoor',        13.2170, 79.1000, 'AP', ARRAY['Tirupati']),
  ('east-godavari',         'EAST GODAVARI',        'Rajamahendravaram',17.0050, 81.7800, 'AP', ARRAY['Rajahmundry']),
  ('eluru',                 'ELURU',                'Eluru',           16.7100, 81.0950, 'AP', ARRAY['West Godavari']),
  ('guntur',                'GUNTUR',               'Guntur',          16.3067, 80.4365, 'AP', NULL),
  ('kakinada',              'KAKINADA',             'Kakinada',        16.9890, 82.2470, 'AP', ARRAY['East Godavari']),
  ('konaseema',             'KONASEEMA',            'Amalapuram',      16.5780, 82.0070, 'AP', ARRAY['Amalapuram','East Godavari']),
  ('krishna',               'KRISHNA',              'Machilipatnam',   16.1875, 81.1389, 'AP', ARRAY['Vijayawada']),
  ('kurnool',               'KURNOOL',              'Kurnool',         15.8281, 78.0373, 'AP', NULL),
  ('nandyal',               'NANDYAL',              'Nandyal',         15.4780, 78.4830, 'AP', ARRAY['Kurnool']),
  ('ntr',                   'NTR',                  'Vijayawada',      16.5062, 80.6480, 'AP', ARRAY['Krishna','Vijayawada']),
  ('palnadu',               'PALNADU',              'Narasaraopet',    16.2350, 80.0490, 'AP', ARRAY['Guntur','Narasaraopet']),
  ('parvathipuram-manyam',  'PARVATHIPURAM MANYAM', 'Parvathipuram',   18.7780, 83.4250, 'AP', ARRAY['Vizianagaram']),
  ('prakasam',              'PRAKASAM',             'Ongole',          15.5057, 80.0499, 'AP', ARRAY['Ongole']),
  ('sri-potti-sriramulu',   'SRI POTTI SRIRAMULU NELLORE', 'Nellore',  14.4426, 79.9865, 'AP', ARRAY['Nellore','SPSR Nellore']),
  ('sri-sathya-sai',        'SRI SATHYA SAI',       'Puttaparthi',     14.1670, 77.8060, 'AP', ARRAY['Anantapur','Puttaparthi']),
  ('srikakulam',            'SRIKAKULAM',           'Srikakulam',      18.2949, 83.8938, 'AP', NULL),
  ('tirupati',              'TIRUPATI',             'Tirupati',        13.6288, 79.4192, 'AP', ARRAY['Chittoor']),
  ('visakhapatnam',         'VISAKHAPATNAM',        'Visakhapatnam',   17.6868, 83.2185, 'AP', ARRAY['Vizag']),
  ('vizianagaram',          'VIZIANAGARAM',         'Vizianagaram',    18.1167, 83.4115, 'AP', NULL),
  ('west-godavari',         'WEST GODAVARI',        'Bhimavaram',      16.5440, 81.5212, 'AP', ARRAY['Bhimavaram']),
  ('ysr',                   'YSR KADAPA',           'Kadapa',          14.4750, 78.8240, 'AP', ARRAY['Kadapa','YSR'])
ON CONFLICT (id) DO UPDATE SET
  name          = EXCLUDED.name,
  hq_city       = EXCLUDED.hq_city,
  centroid_lat  = EXCLUDED.centroid_lat,
  centroid_lon  = EXCLUDED.centroid_lon,
  state_code    = EXCLUDED.state_code,
  aliases       = EXCLUDED.aliases;
