-- CM Page political handles — VERIFIED PARTY OFFICIAL ACCOUNTS ONLY.
--
-- Personal handles for individual leaders are intentionally NOT seeded:
-- a misnamed handle attributes statements to the wrong person and
-- destroys CM-grade trust. Add personal handles only after manually
-- confirming the account on the party's own website / press release.
--
-- All rows here are inserted with active = FALSE. Flip to TRUE only
-- after you confirm each handle is current.
--
-- Apply via: docker exec -i rig-postgres psql -U rig -d rig
--                          < scripts/seeds/cm_political_handles.sql

INSERT INTO cm_political_handles (
    state, coalition, party, person_name, person_role, platform,
    handle, url, verified_url, active, cadence_minutes
) VALUES
    -- Telangana — party official accounts.
    ('TG', 'ruling',     'INC',   NULL, 'Party', 'twitter', '@INCTelangana',  'https://twitter.com/INCTelangana',  NULL, FALSE, 60),
    ('TG', 'opposition', 'BRS',   NULL, 'Party', 'twitter', '@BRSparty',      'https://twitter.com/BRSparty',      NULL, FALSE, 60),
    ('TG', 'opposition', 'BJP',   NULL, 'Party', 'twitter', '@BJP4Telangana', 'https://twitter.com/BJP4Telangana', NULL, FALSE, 60),
    ('TG', 'opposition', 'AIMIM', NULL, 'Party', 'twitter', '@aimim_national','https://twitter.com/aimim_national',NULL, FALSE, 60),
    -- Andhra Pradesh — party official accounts.
    ('AP', 'ruling',     'TDP',   NULL, 'Party', 'twitter', '@JaiTDP',         'https://twitter.com/JaiTDP',         NULL, FALSE, 60),
    ('AP', 'ruling',     'JSP',   NULL, 'Party', 'twitter', '@JanaSenaParty', 'https://twitter.com/JanaSenaParty', NULL, FALSE, 60),
    ('AP', 'ruling',     'BJP',   NULL, 'Party', 'twitter', '@BJP4AndhraPrad','https://twitter.com/BJP4AndhraPrad',NULL, FALSE, 60),
    ('AP', 'opposition', 'YSRCP', NULL, 'Party', 'twitter', '@YSRCParty',     'https://twitter.com/YSRCParty',     NULL, FALSE, 60),
    ('AP', 'opposition', 'INC',   NULL, 'Party', 'twitter', '@INCAndhra',     'https://twitter.com/INCAndhra',     NULL, FALSE, 60)
ON CONFLICT (platform, handle, state) DO NOTHING;
