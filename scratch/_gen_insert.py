import csv

ROOT = r"C:\Users\Dell\Desktop\rig-surveillance\scratch"


def q(s):
    return "'" + str(s).replace("'", "''") + "'"


rows = []
with open(ROOT + r"\_import33.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        cat = r["topics"].strip("{}").strip()
        topics = "ARRAY[" + q(cat) + "]" if cat else "ARRAY[]::text[]"
        tier = r["source_tier"].strip() if r["source_tier"].strip().lstrip("-").isdigit() else "3"
        rows.append("(%s,%s,%s,'rss',%s,%s,%s,%s,false)" % (
            q(r["name"]), q(r["domain"]), q(r["rss_url"]), tier,
            q(r["language"]), q(r["country"]), topics))

sql = (
    "\\set ON_ERROR_STOP on\n"
    "BEGIN;\n"
    "SELECT count(*) AS before_total FROM sources;\n"
    "INSERT INTO sources (name,domain,rss_url,source_type,source_tier,language,country,topics,is_active) VALUES\n"
    + ",\n".join(rows)
    + "\nON CONFLICT (domain) DO NOTHING;\n"
    "SELECT count(*) AS after_total, count(*) FILTER (WHERE is_active=false AND created_at > now() - interval '10 minutes') AS staged_batch FROM sources;\n"
    "COMMIT;\n"
    "\\echo '### per-country staged this batch:'\n"
    "SELECT country, count(*) FROM sources WHERE is_active=false AND source_type='rss' AND created_at > now() - interval '10 minutes' GROUP BY 1 ORDER BY 1;\n"
)
with open(ROOT + r"\_insert33.sql", "w", encoding="utf-8") as f:
    f.write(sql)
print("wrote _insert33.sql with", len(rows), "VALUES rows")
