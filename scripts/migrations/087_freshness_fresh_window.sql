-- 087_freshness_fresh_window.sql
-- =====================================================================
-- Worldwide Phase 0a (corrective): forward-looking freshness.
--
-- WHY: v_freshness_pipeline_lag measures collect->processed lag over rows
-- *processed* in the last 24h — which is dominated by the substrate drain
-- chewing weeks-old backlog (p50 ~36 days). That is true but MISLEADING as
-- a freshness signal. This view instead asks the forward question: of the
-- articles COLLECTED in the last 2h/6h/24h, what fraction are already
-- embedded / nlp'd / substrated? That is the metric the Worldwide
-- clustering freshness SLO actually cares about.
--
-- Views only — no data lock, safe anytime.
-- =====================================================================

CREATE OR REPLACE VIEW v_freshness_fresh_window AS
SELECT w.label                                                                       AS window,
       count(*)                                                                      AS collected,
       count(a.labse_embedding)                                                      AS embedded,
       round(100.0*count(a.labse_embedding)/NULLIF(count(*),0),1)                    AS embedded_pct,
       count(*) FILTER (WHERE a.nlp_processed)                                        AS nlp_done,
       count(*) FILTER (WHERE a.substrate_status = 'ok')                              AS substrate_ok,
       round(100.0*count(*) FILTER (WHERE a.substrate_status = 'ok')/NULLIF(count(*),0),1) AS substrate_pct
FROM (VALUES
        ('1_last_2h',  interval '2 hours'),
        ('2_last_6h',  interval '6 hours'),
        ('3_last_24h', interval '24 hours')
     ) AS w(label, span)
JOIN articles a ON a.collected_at > now() - w.span
GROUP BY w.label
ORDER BY w.label;

GRANT SELECT ON v_freshness_fresh_window TO analytics_user;
GRANT SELECT ON v_freshness_fresh_window TO rigwire_app;
