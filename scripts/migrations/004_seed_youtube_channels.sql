-- P14: Seed Telangana-relevant YouTube channels
-- 63 channels: government, ruling party, opposition, news, police

INSERT INTO youtube_channels (channel_id, channel_name, channel_url, is_active) VALUES

-- Official Government
('UCrL81afpXRAqW0vnGLRj20Q', 'I&PR Telangana',                      'https://youtube.com/channel/UCrL81afpXRAqW0vnGLRj20Q', TRUE),
('UC_gvbd0N1gJEbba4K6LWerg', 'Telangana CMO',                        'https://youtube.com/channel/UC_gvbd0N1gJEbba4K6LWerg', TRUE),
('UC9nvHG9rfjxZB9b8bT8uayQ', 'GHMC Hyderabad',                       'https://youtube.com/channel/UC9nvHG9rfjxZB9b8bT8uayQ', TRUE),
('UCZE4kMm_vY5Dlcu-cd2GdTw', 'TSRTC Official',                       'https://youtube.com/channel/UCZE4kMm_vY5Dlcu-cd2GdTw', TRUE),
('UCewoKzniCol5XCRC5TXDy3A', 'TSRTC',                                'https://youtube.com/channel/UCewoKzniCol5XCRC5TXDy3A', TRUE),
('UCzDockV5MUqWbSDdbLguBuw', 'Telangana Police',                      'https://youtube.com/channel/UCzDockV5MUqWbSDdbLguBuw', TRUE),
('UCKukFPLCTQoYWqscVM2r4Rg', 'Telangana Special Police',              'https://youtube.com/channel/UCKukFPLCTQoYWqscVM2r4Rg', TRUE),
('UCrGoDA_dFKrbgs5C5Tjcz6A', 'TSPSC Official',                       'https://youtube.com/channel/UCrGoDA_dFKrbgs5C5Tjcz6A', TRUE),
('UC2t0yf5X9OEktsdXTrUsK4w', 'High Court Telangana',                 'https://youtube.com/channel/UC2t0yf5X9OEktsdXTrUsK4w', TRUE),
('UClQ5YT17yP90ggEjAoAd32Q', 'Hyderabad Metro Rail',                 'https://youtube.com/channel/UClQ5YT17yP90ggEjAoAd32Q', TRUE),
('UCrEfOlAzm8TWrqIYi5TuTQQ', 'DD News Telangana',                    'https://youtube.com/channel/UCrEfOlAzm8TWrqIYi5TuTQQ', TRUE),
('UCcsvAreQ1IxIjWlBSpNEOWg', 'DD Saptagiri',                         'https://youtube.com/channel/UCcsvAreQ1IxIjWlBSpNEOWg', TRUE),
('UC73x-IA5uTPvT8ExvXZnGgw', 'Cyberabad Traffic Police',             'https://youtube.com/channel/UC73x-IA5uTPvT8ExvXZnGgw', TRUE),
('UCf7K6CpwOLuQN72F1iFaqfA', 'Cyberabad Police Official',            'https://youtube.com/channel/UCf7K6CpwOLuQN72F1iFaqfA', TRUE),
('UCLwvrg0nsmIel7BV_ulSRoA', 'Hyderabad City Police',                'https://youtube.com/channel/UCLwvrg0nsmIel7BV_ulSRoA', TRUE),
('UC7RaDgwh6u6sbqyczE978qA', 'Minister for Irrigation Telangana',    'https://youtube.com/channel/UC7RaDgwh6u6sbqyczE978qA', TRUE),

-- Ruling Party (INC Telangana)
('UC5XjG1oQVNIKZM8bQhA7Yrw', 'Revanth Reddy CM Official',           'https://youtube.com/channel/UC5XjG1oQVNIKZM8bQhA7Yrw', TRUE),
('UCFpnEY2_Ps_B0fA3UVptPQg', 'Revanth Reddy Official',              'https://youtube.com/channel/UCFpnEY2_Ps_B0fA3UVptPQg', TRUE),
('UCwRh9VikCe1qi16kPFjTIGg', 'Telangana Congress Studio',           'https://youtube.com/channel/UCwRh9VikCe1qi16kPFjTIGg', TRUE),
('UCjfYRVmU3JrKN78mLJHHUPQ', 'Indian National Congress',            'https://youtube.com/channel/UCjfYRVmU3JrKN78mLJHHUPQ', TRUE),
('UCf0nh3fykbvy_Wq4TRiwByQ', 'Bhatti Vikramarka Mallu',             'https://youtube.com/channel/UCf0nh3fykbvy_Wq4TRiwByQ', TRUE),
('UCKccN9PRGfOpHfBCMyJoGtA', 'Mana Bhatti Vikramarka',              'https://youtube.com/channel/UCKccN9PRGfOpHfBCMyJoGtA', TRUE),
('UCBixs4_jkB_EzK4g7SkbnEg', 'Bhatti Vikramarka',                   'https://youtube.com/channel/UCBixs4_jkB_EzK4g7SkbnEg', TRUE),

-- Opposition (BRS / TRS)
('UCDNhtX8lDoGwxchhOi8_gyQ', 'BRS Party',                           'https://youtube.com/channel/UCDNhtX8lDoGwxchhOi8_gyQ', TRUE),
('UC18m-lkuzbIyboBTVE6HDuw', 'K.T. Rama Rao KTR',                   'https://youtube.com/channel/UC18m-lkuzbIyboBTVE6HDuw', TRUE),
('UCLp2RsRbPxD58OL9__4pZ-A', 'KTR Official',                        'https://youtube.com/channel/UCLp2RsRbPxD58OL9__4pZ-A', TRUE),
('UC-yixraxXUVVJd4LStsCNig', 'KTR Official (2)',                     'https://youtube.com/channel/UC-yixraxXUVVJd4LStsCNig', TRUE),
('UCDeruoCpL6of29kClngpftw', 'Harish Rao Thanneeru',                'https://youtube.com/channel/UCDeruoCpL6of29kClngpftw', TRUE),
('UCdFW2PDhHkDBWVrCpOWnokA', 'Harish Rao Tanneru',                  'https://youtube.com/channel/UCdFW2PDhHkDBWVrCpOWnokA', TRUE),
('UCtFIoCWO3Ihff6wGAYTJIcg', 'BRS Live Feed',                       'https://youtube.com/channel/UCtFIoCWO3Ihff6wGAYTJIcg', TRUE),
('UCrJHSyOgRXCEAz8uZ0y02kA', 'BRS Party Official',                  'https://youtube.com/channel/UCrJHSyOgRXCEAz8uZ0y02kA', TRUE),
('UCJBh39odBeNHU3LSQQDOKVw', 'BRS Connects',                        'https://youtube.com/channel/UCJBh39odBeNHU3LSQQDOKVw', TRUE),

-- Other Parties (opposition monitoring)
('UCclPsid7e9wByzG0AdV1nrQ', 'AIMIM Official',                      'https://youtube.com/channel/UCclPsid7e9wByzG0AdV1nrQ', TRUE),
('UCjOBq97vcsaiv_fYJ5OoRjQ', 'AIMIM',                               'https://youtube.com/channel/UCjOBq97vcsaiv_fYJ5OoRjQ', TRUE),
('UCvMZV13-yh2sUQY2s0Y5hlg', 'Telugu Desam Party Official',         'https://youtube.com/channel/UCvMZV13-yh2sUQY2s0Y5hlg', TRUE),
('UCrKevLQTcgUp2kZ-WE0pWZQ', 'JanaSena Party',                      'https://youtube.com/channel/UCrKevLQTcgUp2kZ-WE0pWZQ', TRUE),
('UC8dHVWzZV7gRqUJtiXyEC-g', 'JanaSena Official',                   'https://youtube.com/channel/UC8dHVWzZV7gRqUJtiXyEC-g', TRUE),

-- Major Telugu News (primary)
('UCPXTXMecYqnRKNdqdVOGSFg', 'TV9 Telugu Live',                     'https://youtube.com/channel/UCPXTXMecYqnRKNdqdVOGSFg', TRUE),
('UCg6JyAGrskayg14qJP3598g', 'TV9 Telugu Digital',                  'https://youtube.com/channel/UCg6JyAGrskayg14qJP3598g', TRUE),
('UCQ_FATLW83q-4xJ2fsi8qAw', 'Sakshi TV Live',                      'https://youtube.com/channel/UCQ_FATLW83q-4xJ2fsi8qAw', TRUE),
('UCZ9m4KOh8Ei60428xeGYDCQ', 'Sakshi TV',                           'https://youtube.com/channel/UCZ9m4KOh8Ei60428xeGYDCQ', TRUE),
('UCumtYpCY26F6Jr3satUgMvA', 'NTV Telugu',                          'https://youtube.com/channel/UCumtYpCY26F6Jr3satUgMvA', TRUE),
('UCtzYV2L-m8ew93mZb3qhf5w', 'NTV Live',                            'https://youtube.com/channel/UCtzYV2L-m8ew93mZb3qhf5w', TRUE),
('UC_2irx_BQR7RsBKmUV9fePQ', 'ABN Telugu',                          'https://youtube.com/channel/UC_2irx_BQR7RsBKmUV9fePQ', TRUE),
('UCAR3h_9fLV82N2FH4cE4RKw', 'TV5 News',                            'https://youtube.com/channel/UCAR3h_9fLV82N2FH4cE4RKw', TRUE),
('UCNZOrs1QBt8cJnv9ud96qRA', 'hmtv Telugu News',                    'https://youtube.com/channel/UCNZOrs1QBt8cJnv9ud96qRA', TRUE),
('UCVGRzd9YUtXYozquyYcjQOQ', 'Raj News Telugu',                     'https://youtube.com/channel/UCVGRzd9YUtXYozquyYcjQOQ', TRUE),
('UCZ5WdwMXLtBH47gdrIVHt5g', 'Raj News Telangana',                  'https://youtube.com/channel/UCZ5WdwMXLtBH47gdrIVHt5g', TRUE),
('UC51p-_H_xiBig2wV5UP_uVQ', 'Bharat Today Telugu',                 'https://youtube.com/channel/UC51p-_H_xiBig2wV5UP_uVQ', TRUE),
('UCu6edg8_eu3-A8ylgaWereA', 'T News Telugu',                       'https://youtube.com/channel/UCu6edg8_eu3-A8ylgaWereA', TRUE),
('UCD84CA3aMnTH9AFWBSPC1ow', 'T News Telugu Live',                  'https://youtube.com/channel/UCD84CA3aMnTH9AFWBSPC1ow', TRUE),
('UCDCMjD1XIAsCZsYHNMGVcog', 'V6 News Telugu',                      'https://youtube.com/channel/UCDCMjD1XIAsCZsYHNMGVcog', TRUE),
('UC2PWc0zFDtZBXgFXPZBb5zg', 'V6 Velugu News',                      'https://youtube.com/channel/UC2PWc0zFDtZBXgFXPZBb5zg', TRUE),
('UC986Hrkimq5gGR-Ikva6VfA', 'Studio N Telugu',                     'https://youtube.com/channel/UC986Hrkimq5gGR-Ikva6VfA', TRUE),
('UCXIYJuRMzQZwdaK3wLpfjfA', 'Telangana Today',                     'https://youtube.com/channel/UCXIYJuRMzQZwdaK3wLpfjfA', TRUE),
('UC4jYxQXFqB5q6INV6WEQC2A', 'iNews Telugu',                        'https://youtube.com/channel/UC4jYxQXFqB5q6INV6WEQC2A', TRUE),
('UCay237aXF75tZM4l1P6zFHg', 'iNews',                               'https://youtube.com/channel/UCay237aXF75tZM4l1P6zFHg', TRUE),
('UCfWo0Z5PKYd86JfQ5ZE5cWg', 'Zee Telugu News',                     'https://youtube.com/channel/UCfWo0Z5PKYd86JfQ5ZE5cWg', TRUE),
('UC6ickpgDIsltU_-8CbZaksQ', 'ETV Telangana',                       'https://youtube.com/channel/UC6ickpgDIsltU_-8CbZaksQ', TRUE),
('UCE-4Rs8rZ2VRSkfIOAbZuHA', 'ETV Bharat Telangana',                'https://youtube.com/channel/UCE-4Rs8rZ2VRSkfIOAbZuHA', TRUE),
('UCMxG2NC73psxiLzQzb5FvSA', 'MOJO Telugu Media',                   'https://youtube.com/channel/UCMxG2NC73psxiLzQzb5FvSA', TRUE),
('UCBcY9Enea1PNBpzafGcKl-A', 'Aadab Hyderabad News',                'https://youtube.com/channel/UCBcY9Enea1PNBpzafGcKl-A', TRUE),
('UC8lVvurdhqV2-cTizQjh4wQ', 'Siasat Daily',                        'https://youtube.com/channel/UC8lVvurdhqV2-cTizQjh4wQ', TRUE),
('UCtrZ2EYLdLVR9G1eKCfN4pg', 'Siasat TV',                           'https://youtube.com/channel/UCtrZ2EYLdLVR9G1eKCfN4pg', TRUE),
('UCnlfu6BIvdsW9U7UwawXz8Q', 'Telangana Focus',                     'https://youtube.com/channel/UCnlfu6BIvdsW9U7UwawXz8Q', TRUE),
('UC9JdWA6EuHdNKZkGEsRYE5A', 'Voice TV Telugu News',                'https://youtube.com/channel/UC9JdWA6EuHdNKZkGEsRYE5A', TRUE),
('UCBnQF4yu8du8ypDFnqUDlwA', '4TV News Channel',                    'https://youtube.com/channel/UCBnQF4yu8du8ypDFnqUDlwA', TRUE),
('UCr-h3VORUAv-q0R8dmBszlg', 'Deccan Daily',                        'https://youtube.com/channel/UCr-h3VORUAv-q0R8dmBszlg', TRUE),
('UCg-zv4qWOcsgcQ53PpePr5Q', 'Telangana News',                      'https://youtube.com/channel/UCg-zv4qWOcsgcQ53PpePr5Q', TRUE),
('UC_2jdhTx6I20v8WftDf7m3A', 'Telangana Velugu',                    'https://youtube.com/channel/UC_2jdhTx6I20v8WftDf7m3A', TRUE),
('UCoM6qP3aq_R6_1G2DoCNnTA', 'Mana Telangana',                      'https://youtube.com/channel/UCoM6qP3aq_R6_1G2DoCNnTA', TRUE),
('UCJi8M0hRKjz8SLPvJKEVTOg', 'ETV Andhra Pradesh',                  'https://youtube.com/channel/UCJi8M0hRKjz8SLPvJKEVTOg', TRUE)

ON CONFLICT (channel_id) DO NOTHING;

SELECT COUNT(*) AS total_channels FROM youtube_channels;
