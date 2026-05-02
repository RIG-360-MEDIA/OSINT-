-- districts_telangana.sql
-- 33-row Telangana districts gazetteer for CM Page v2.
--
-- Centroids derived from frontend/src/app/brief/cm/editorial/telangana-geo.ts,
-- which itself was generated from geoBoundaries gbOpen IND ADM2 (2021)
-- via frontend/scripts/fetch-telangana-geo.mjs. Lat/lon are the polygon
-- centroids; small drift (~1-3km) from official HQ-city geocoding is
-- acceptable for atlas rendering.
--
-- Apply via:
--   docker exec -i rig-postgres psql -U rig -d rig \
--     < scripts/seeds/districts_telangana.sql

INSERT INTO districts (id, state_code, name, hq_city, centroid_lat, centroid_lon, aliases) VALUES
  ('adilabad', 'TG', 'ADILABAD', 'Adilabad', 19.6500, 78.5208, '{}'::TEXT[]),
  ('bhadradri', 'TG', 'BHADRADRI', 'Bhadradri', 17.9869, 80.9024, ARRAY['KOTHAGUDEM', 'BHADRADRI KOTHAGUDEM']::TEXT[]),
  ('hanumakonda', 'TG', 'HANUMAKONDA', 'Hanumakonda', 18.0603, 79.5128, ARRAY['HANAMKONDA', 'WARANGAL URBAN']::TEXT[]),
  ('hyderabad', 'TG', 'HYDERABAD', 'Hyderabad', 17.4199, 78.4815, ARRAY['HYD']::TEXT[]),
  ('jagtial', 'TG', 'JAGTIAL', 'Jagtial', 18.8862, 78.8464, '{}'::TEXT[]),
  ('jangaon', 'TG', 'JANGAON', 'Jangaon', 17.7601, 79.2787, '{}'::TEXT[]),
  ('jayashankar', 'TG', 'JAYASHANKAR', 'Jayashankar', 18.5146, 79.9478, ARRAY['BHUPALPALLY', 'JAYASHANKAR BHUPALPALLY']::TEXT[]),
  ('jogulamba', 'TG', 'JOGULAMBA', 'Jogulamba', 16.0370, 77.7390, ARRAY['GADWAL', 'JOGULAMBA GADWAL']::TEXT[]),
  ('kamareddy', 'TG', 'KAMAREDDY', 'Kamareddy', 18.2898, 77.9751, '{}'::TEXT[]),
  ('karimnagar', 'TG', 'KARIMNAGAR', 'Karimnagar', 18.3712, 79.3094, '{}'::TEXT[]),
  ('khammam', 'TG', 'KHAMMAM', 'Khammam', 17.1083, 80.3540, '{}'::TEXT[]),
  ('komaram-bheem', 'TG', 'KUMRAM BHEEM', 'Kumram Bheem', 19.4419, 79.4881, ARRAY['KUMRAM', 'KOMURAM BHEEM', 'ASIFABAD', 'KUMURAM BHEEM ASIFABAD']::TEXT[]),
  ('mahabubabad', 'TG', 'MAHABUBABAD', 'Mahabubabad', 17.5453, 79.9691, '{}'::TEXT[]),
  ('mahbubnagar', 'TG', 'MAHBUBNAGAR', 'Mahbubnagar', 16.7381, 77.8591, ARRAY['MAHABUBNAGAR', 'PALAMOORU']::TEXT[]),
  ('mancherial', 'TG', 'MANCHERIAL', 'Mancherial', 18.9369, 79.5549, '{}'::TEXT[]),
  ('medak', 'TG', 'MEDAK', 'Medak', 18.0476, 78.2713, '{}'::TEXT[]),
  ('medchal', 'TG', 'MEDCHAL', 'Medchal', 17.5246, 78.5469, ARRAY['MEDCHAL MALKAJGIRI', 'MALKAJGIRI']::TEXT[]),
  ('mulugu', 'TG', 'MULUGU', 'Mulugu', 18.2904, 80.2927, '{}'::TEXT[]),
  ('nagarkurnool', 'TG', 'NAGARKURNOOL', 'Nagarkurnool', 16.3665, 78.6923, '{}'::TEXT[]),
  ('nalgonda', 'TG', 'NALGONDA', 'Nalgonda', 16.7468, 78.9845, '{}'::TEXT[]),
  ('narayanpet', 'TG', 'NARAYANPET', 'Narayanpet', 16.6334, 77.5229, '{}'::TEXT[]),
  ('nirmal', 'TG', 'NIRMAL', 'Nirmal', 19.0923, 78.1232, '{}'::TEXT[]),
  ('nizamabad', 'TG', 'NIZAMABAD', 'Nizamabad', 18.7434, 78.2313, '{}'::TEXT[]),
  ('peddapalli', 'TG', 'PEDDAPALLI', 'Peddapalli', 18.6707, 79.5228, '{}'::TEXT[]),
  ('rajanna-sircilla', 'TG', 'RAJANNA SIRCILLA', 'Rajanna Sircilla', 18.3805, 78.7030, ARRAY['RAJANNA', 'SIRCILLA', 'RAJANNA SIRCILLA']::TEXT[]),
  ('rangareddy', 'TG', 'RANGAREDDY', 'Rangareddy', 17.2171, 78.4228, ARRAY['RANGA REDDY', 'RANGAREDDI', 'RR DISTRICT']::TEXT[]),
  ('sangareddy', 'TG', 'SANGAREDDY', 'Sangareddy', 17.7981, 77.7970, '{}'::TEXT[]),
  ('siddipet', 'TG', 'SIDDIPET', 'Siddipet', 17.9742, 78.8117, '{}'::TEXT[]),
  ('suryapet', 'TG', 'SURYAPET', 'Suryapet', 17.1237, 79.8117, '{}'::TEXT[]),
  ('vikarabad', 'TG', 'VIKARABAD', 'Vikarabad', 17.2858, 77.6903, '{}'::TEXT[]),
  ('wanaparthy', 'TG', 'WANAPARTHY', 'Wanaparthy', 16.2358, 78.0792, '{}'::TEXT[]),
  ('warangal', 'TG', 'WARANGAL', 'Warangal', 18.0056, 79.7103, ARRAY['WARANGAL RURAL']::TEXT[]),
  ('yadadri', 'TG', 'YADADRI', 'Yadadri', 17.4932, 78.9498, ARRAY['BHUVANAGIRI', 'BHONGIR', 'YADADRI BHUVANAGIRI']::TEXT[])
ON CONFLICT (id) DO UPDATE SET
    state_code   = EXCLUDED.state_code,
    name         = EXCLUDED.name,
    hq_city      = EXCLUDED.hq_city,
    centroid_lat = EXCLUDED.centroid_lat,
    centroid_lon = EXCLUDED.centroid_lon,
    aliases      = EXCLUDED.aliases;
