#!/bin/bash
# full_db_audit.sh — Comprehensive per-table per-column data quality audit.
#
# Generates /tmp/DB_AUDIT_<date>.md on Hetzner host with:
#   - per-table row count
#   - per-column NULL%, cardinality, sample values
#   - per-numeric/text min/max/avg
#   - cross-table consistency checks
#
# Run on Hetzner host: bash /tmp/full_db_audit.sh
# Output: /tmp/DB_AUDIT.md

set -e
OUT="/tmp/DB_AUDIT.md"
DB="docker exec rig-postgres psql -U rig -d rig -t -A -F ' | '"
DBHEAD="docker exec rig-postgres psql -U rig -d rig"

echo "# RIG-Surveillance Database Quality Audit" > "$OUT"
echo "" >> "$OUT"
echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT"
echo "" >> "$OUT"

# ───────── 1. TOP-LEVEL TABLE INVENTORY ─────────
echo "## Table inventory (public schema)" >> "$OUT"
echo "" >> "$OUT"
echo "| Table | Rows | Columns |" >> "$OUT"
echo "|---|---:|---:|" >> "$OUT"
$DB -c "
SELECT format('| %s | %s | %s |',
    c.relname,
    to_char(c.reltuples::bigint, 'FM999G999G999'),
    (SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name=c.relname))
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind='r' AND n.nspname='public'
ORDER BY c.reltuples DESC;
" >> "$OUT" 2>/dev/null
echo "" >> "$OUT"

# ───────── 2. PER-TABLE DEEP DIVE ─────────
# Pull tables, biggest first
TABLES=$($DB -c "
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind='r' AND n.nspname='public'
ORDER BY c.reltuples DESC;
" | grep -v '^$' | head -60)

for T in $TABLES; do
    echo "" >> "$OUT"
    echo "## \`$T\`" >> "$OUT"

    # exact row count
    ROWCOUNT=$($DB -c "SELECT count(*) FROM \"$T\";" 2>/dev/null | tr -d ' ' | head -1)
    echo "" >> "$OUT"
    echo "**Rows:** $ROWCOUNT" >> "$OUT"
    echo "" >> "$OUT"

    if [ "$ROWCOUNT" = "0" ] || [ -z "$ROWCOUNT" ]; then
        echo "_(empty table — skipped detail)_" >> "$OUT"
        continue
    fi

    # column inventory
    echo "| Column | Type | NULL% | Distinct | Notes |" >> "$OUT"
    echo "|---|---|---:|---:|---|" >> "$OUT"

    # Get column list with types
    COLS_JSON=$($DB -c "
    SELECT json_agg(json_build_object(
        'name', column_name,
        'type', data_type,
        'nullable', is_nullable
    ))
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='$T'
    ORDER BY ordinal_position;
    " 2>/dev/null)

    # For each column, query null% and distinct count
    COLS=$($DB -c "
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='public' AND table_name='$T'
    ORDER BY ordinal_position;
    " 2>/dev/null | grep -v '^$')

    for COL in $COLS; do
        TYPE=$($DB -c "
        SELECT data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name='$T' AND column_name='$COL';
        " 2>/dev/null | head -1 | tr -d ' ')

        # NULL%
        NULL_PCT=$($DB -c "
        SELECT round(100.0 * sum(CASE WHEN \"$COL\" IS NULL THEN 1 ELSE 0 END) / nullif(count(*),0), 1)
        FROM \"$T\";
        " 2>/dev/null | head -1 | tr -d ' ')

        # Distinct (capped via approx_count_distinct alternative — use a hash-based approximation for big tables)
        if [ "$ROWCOUNT" -gt 1000000 ]; then
            DISTINCT=$($DB -c "
            SELECT count(DISTINCT \"$COL\")
            FROM (SELECT \"$COL\" FROM \"$T\" TABLESAMPLE SYSTEM(2) LIMIT 100000) s;
            " 2>/dev/null | head -1 | tr -d ' ')
            DISTINCT="~${DISTINCT} (sampled)"
        else
            DISTINCT=$($DB -c "SELECT count(DISTINCT \"$COL\") FROM \"$T\";" 2>/dev/null | head -1 | tr -d ' ')
        fi

        # Notes — type-specific quality signal
        NOTES=""
        case "$TYPE" in
            text|character|varchar|character_varying)
                STATS=$($DB -c "
                SELECT format('avg_len=%s, max_len=%s', round(avg(length(\"$COL\")))::text, max(length(\"$COL\")))
                FROM \"$T\" WHERE \"$COL\" IS NOT NULL;
                " 2>/dev/null | head -1)
                NOTES="$STATS"
                ;;
            integer|bigint|smallint|numeric|double_precision|real)
                STATS=$($DB -c "
                SELECT format('min=%s max=%s avg=%s', min(\"$COL\")::text, max(\"$COL\")::text, round(avg(\"$COL\")::numeric, 2)::text)
                FROM \"$T\" WHERE \"$COL\" IS NOT NULL;
                " 2>/dev/null | head -1)
                NOTES="$STATS"
                ;;
            'timestamp with time zone'|'timestamp without time zone'|date)
                STATS=$($DB -c "
                SELECT format('min=%s max=%s', min(\"$COL\")::text, max(\"$COL\")::text)
                FROM \"$T\" WHERE \"$COL\" IS NOT NULL;
                " 2>/dev/null | head -1)
                NOTES="$STATS"
                ;;
            boolean)
                STATS=$($DB -c "
                SELECT format('true=%s, false=%s', sum(CASE WHEN \"$COL\" THEN 1 ELSE 0 END)::text, sum(CASE WHEN NOT \"$COL\" THEN 1 ELSE 0 END)::text)
                FROM \"$T\" WHERE \"$COL\" IS NOT NULL;
                " 2>/dev/null | head -1)
                NOTES="$STATS"
                ;;
            'USER-DEFINED'|uuid|jsonb|json|ARRAY)
                NOTES=""
                ;;
        esac

        # Distinct values for low-cardinality columns (≤15)
        if [ -n "$DISTINCT" ] && [ "$DISTINCT" != "" ] && [ "${DISTINCT:0:1}" != "~" ]; then
            if [ "$DISTINCT" -le 15 ] && [ "$DISTINCT" -gt 0 ]; then
                TOP=$($DB -c "
                SELECT string_agg(format('%s(%s)', coalesce(v::text, 'NULL'), n::text), ' ')
                FROM (SELECT \"$COL\" AS v, count(*) AS n FROM \"$T\" GROUP BY 1 ORDER BY 2 DESC LIMIT 10) x;
                " 2>/dev/null | head -1)
                if [ -n "$TOP" ] && [ "$TOP" != "" ]; then
                    NOTES="${NOTES} · ${TOP}"
                fi
            fi
        fi

        # Escape pipes in notes
        NOTES_CLEAN=$(echo "$NOTES" | sed 's/|/\\|/g')

        echo "| \`$COL\` | $TYPE | $NULL_PCT% | $DISTINCT | $NOTES_CLEAN |" >> "$OUT"
    done
done

# ───────── 3. CROSS-TABLE QUALITY CHECKS ─────────
echo "" >> "$OUT"
echo "## Cross-table consistency" >> "$OUT"
echo "" >> "$OUT"

echo "### Substrate pipeline coverage" >> "$OUT"
$DB -c "
SELECT format('| %s | %s |', substrate_status, count(*))
FROM articles
GROUP BY substrate_status
ORDER BY count(*) DESC;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### extraction_version distribution" >> "$OUT"
$DB -c "
SELECT format('| v%s | %s |', coalesce(extraction_version::text,'NULL'), count(*))
FROM articles WHERE substrate_status='ok'
GROUP BY extraction_version ORDER BY 1;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### article_type distribution" >> "$OUT"
$DB -c "
SELECT format('| %s | %s |', coalesce(article_type,'NULL'), count(*))
FROM articles WHERE substrate_status='ok'
GROUP BY article_type ORDER BY count(*) DESC;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### Article claims FK consistency" >> "$OUT"
$DB -c "
WITH orphans AS (
  SELECT count(*) AS n
  FROM article_claims c
  LEFT JOIN articles a ON a.id = c.article_id
  WHERE a.id IS NULL
)
SELECT format('FK orphan claims: %s', n) FROM orphans;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### D1 SPO progress" >> "$OUT"
$DB -c "
SELECT format(
  'SPO populated: %s / %s (%s%%) — subject only: %s, predicate only: %s, object only: %s, all three: %s',
  count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NOT NULL AND object_text IS NOT NULL),
  count(*),
  round(100.0 * count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NOT NULL AND object_text IS NOT NULL) / nullif(count(*),0), 1),
  count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NULL),
  count(*) FILTER (WHERE predicate IS NOT NULL AND object_text IS NULL),
  count(*) FILTER (WHERE object_text IS NOT NULL AND subject_text IS NULL),
  count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NOT NULL AND object_text IS NOT NULL)
) FROM article_claims;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### Quote language distribution" >> "$OUT"
$DB -c "
SELECT format('| %s | %s |', coalesce(a.language_iso, 'NULL'), count(*))
FROM article_quotes q JOIN articles a ON a.id = q.article_id
GROUP BY a.language_iso ORDER BY count(*) DESC LIMIT 15;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "### Embedding coverage" >> "$OUT"
$DB -c "
SELECT format('| article_claims.embedding | %s / %s (%s%%) |',
  count(*) FILTER (WHERE embedding IS NOT NULL),
  count(*),
  round(100.0 * count(*) FILTER (WHERE embedding IS NOT NULL) / nullif(count(*),0), 1)
) FROM article_claims;
" >> "$OUT" 2>/dev/null
$DB -c "
SELECT format('| articles.labse_embedding | %s / %s (%s%%) |',
  count(*) FILTER (WHERE labse_embedding IS NOT NULL),
  count(*),
  round(100.0 * count(*) FILTER (WHERE labse_embedding IS NOT NULL) / nullif(count(*),0), 1)
) FROM articles;
" >> "$OUT" 2>/dev/null

echo "" >> "$OUT"
echo "_Audit complete._" >> "$OUT"

# Print byte size + first 100 lines so caller can sanity check
wc -l "$OUT"
echo "==="
head -80 "$OUT"
